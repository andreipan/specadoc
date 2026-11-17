<!-- source-sha256: 26f11a5d5427aa85a2e2373146a61a4c826cb4a398cd01b54ad875e7ea82ee6b -->
# Устранение неполадок

[English](../../en/guides/troubleshooting.md)

На этой странице собраны частые отказы гейтов и ошибки с причинами и исправлениями. Тексты сообщений взяты из скриптов. Части в угловых скобках, например `<slug>` или `<path>`, меняются от запуска к запуску.

`<skill-root>` — установленная папка `skills/specadoc`. См. [Установка Specadoc](install.md#проверка-установки).

## Сначала прочитайте вывод

`specadoc_step.py` выводит пять полей для каждого шага:

```text
checked: <what ran>
result: PASS | FAIL | BLOCKED | ...
changed files: <paths or ->
blocking reason: <reason or ->
next: <the next allowed step>
```

Код выхода 0 означает PASS, ACCEPTED, CHECKED и EXTERNAL-PENDING. Код 1 означает FAIL: найдена проблема, которую можно исправить. Код 2 означает BLOCKED (шаг не может выполнить проверку) или NEEDS_DECISION. Причину ищите в `blocking reason`, исправление в `next`. Если шаг вызвал исключение, результат будет `BLOCKED`, а `next` будет `inspect the plan and handoff files, then retry`.

`validate_change.py` выводит по одной строке на нарушение, `<file>:<line>: <message>`, а затем `<n> violation(s) in phase <phase>`. Скрипт завершается с кодом 1, когда находит нарушения, и с кодом 2, когда не может прочитать изменение. Предупреждения начинаются с `warning:` и не блокируют работу.

Если вы не знаете, какой шаг следующий, запустите `python3 <skill-root>/scripts/specadoc_step.py status <slug>`. Его строка `next:` называет следующий разрешённый шаг.

## Версия Python

| Сообщение | Причина | Исправление |
|---|---|---|
| `error: Specadoc scripts need Python 3.10+; this is <version> at <path>. ...` | `python3` в `PATH` старше 3.10. Терминал без `PATH` вашего входа в систему часто находит системный Python | Поставьте Python 3.10 или новее первым в `PATH` или вызовите этот интерпретатор по полному пути |
| `Codex registry resolution requires Python 3.11+; select a supported interpreter` | В проекте есть файлы ролей Codex (`.codex/agents/<role>.toml`). Python 3.10 не умеет читать TOML | Используйте Python 3.11 или новее |

## Отказы validate_change

Контроллер запускает `validate_change.py <slug> --phase <spec|plan|pre-review|final>` перед каждой контрольной точкой. Успешный запуск скрипта проверяет только структуру. Он не доказывает, что требование верно.

| Сообщение | Причина | Исправление |
|---|---|---|
| `error: no change directory: <path>` | Неверный слаг или другой корень артефактов | Проверьте слаг через `list_changes.py`. Проверьте корень, который выводит `doctor.py` |
| `unfilled template placeholder: <text>; wrap code such as list<T> in backticks if it is not a placeholder` | В файле остался текст шаблона в `<...>` | Замените заполнитель. Если это код, заключите его в обратные кавычки |
| `missing required section: ## <name>` | Раздел шаблона удалён | Восстановите раздел из `assets/plan-template.md` или `assets/spec-template.md` |
| `<R>: no acceptance scenario covers it` | У требования нет сценария | Добавьте сценарий с `**Covers:** <R>` |
| `<A>: missing Given` (или `When`, `Then`) | Сценарий неполный | Добавьте недостающую строку |
| `no capability file declared under <root>/specs/` | `## Affected capabilities` не называет ни одной спецификации возможности | Добавьте операции, например `ADDED C1 (R1) — <effect>` |
| `Owner: worker needs Decision risk: low; close the decision and set low, or set Owner: controller with a Controller justification` | У задачи worker ещё есть открытое решение | Закройте решение или передайте задачу контроллеру с указанием причины |
| `<T>: Evidence predates a later change (<reason>); re-verify with specadoc_step.py refresh` | Более поздняя правка затронула файлы принятой задачи | Запустите `specadoc_step.py refresh <slug>` |
| `final verification unchecked: <label>` | У пункта в `## Final verification` нет доказательства | Запустите `specadoc_step.py finalize <slug>`. Не отмечайте пункты вручную |
| `` verification.final: no `finalize --run` record; run specadoc_step.py finalize <slug> --run `` | `.specadoc.json` задаёт `verification.final`, но полный набор тестов не запускали через `finalize` | Запустите `finalize <slug> --run` |
| `Review result: latest round <G> outcome is FAIL, not PASS` | Последний раунд ревью не пройден | Исправьте замечания и запустите повторное ревью |

## Одобрение

| Сообщение | Причина | Исправление |
|---|---|---|
| `plan approval is required before apply or dispatch` | У плана нет записанного одобрения | Одобрите план в чате. Контроллер запускает `specadoc_step.py approve` |
| `plan.md has no Bindings shown; pass --bindings` | Превью не записало привязки ролей | Покажите тому, кто одобряет, привязки из `next`. Затем запустите `approve` с `--bindings` |
| `<G> is recorded but not reviewed; an approval change now would make it stale` | Раунд ревью открыт | Запустите `pre-review <slug> --withdraw`, затем `approve`, затем снова `pre-review` |
| `<files> changed since approval; a round recorded now would settle stale` | `spec.md` или `design.md` изменились после одобрения | Одобрите снова: `approve <slug> --by user --source '<decision>'`. Затем запустите `pre-review` |

## dispatch и accept

| Сообщение | Причина | Исправление |
|---|---|---|
| `controller context is <n> tokens, at least 200k` | Сессия контроллера слишком большая для следующей задачи | Сохраните заметки командой `specadoc_step.py handoff <slug> --file -`. Продолжите в новой сессии с `status <slug>` |
| `design review missing: run specadoc_step.py design-brief, an independent reviewer, then design-review` | В плане есть `## Class inventory`, но нет ревью дизайна | Пройдите гейт дизайна. См. [справочник по гейту дизайна](../../../skills/specadoc/references/design-gate.md) |
| `design review predates the current Class inventory; review the changed inventory again` | Реестр классов изменился после PASS ревью дизайна | Проведите ревью дизайна снова |
| `Verification must contain only exact backticked commands separated by semicolons; ...` | В поле `Verification` есть текст или ручная проверка | Оставьте только команды. Перенесите ручную проверку в `External verification:` |
| `<T>: dependency <T> accepted evidence is stale (<reason>); run specadoc_step.py refresh <slug>; reopen only for code fixes` | Более поздняя правка сделала доказательства завершённой задачи устаревшими | Запустите `refresh <slug>`. Для изменённых файлов `dispatch` делает это сам |
| `changes outside the task scope` | Worker изменил файл, которого нет в задаче | Откатите файл. Или запустите `amend <slug> <T> --allow <path> --reason '<decision>'`, а для сгенерированного файла `--derived <path>` |
| `Class inventory files not created` | Запланированного файла нет | Создайте файл или измените реестр классов и проведите новое ревью дизайна |
| `` `<command>` exited <code> `` | Команда из `Verification` завершилась с ошибкой | Исправьте код или верните задачу worker вместе с ошибкой |
| `worker report is missing: <path>` | Worker не запустил `report` | Попросите worker завершить работу командой `specadoc_step.py report` |
| `worker status <status> is not completion; ...` | В отчёте статус BLOCKED или NEEDS_CONTEXT | Устраните блокер. Затем запустите `accept` с `--resolved '<who removed it and how>'`. Никогда не редактируйте отчёт worker |
| `worker concerns require a controller disposition` (результат `NEEDS_DECISION`) | Worker сообщил о сомнениях | Примите решение и снова запустите `accept` с `--note '<decision>'`. Результат проверки используется повторно |
| `verification timed out after 600s` | Команда работала дольше `--verification-timeout` (по умолчанию 600 секунд) | Сначала найдите причину в журнале. При повторной попытке сохраните тот же базовый снимок |
| `environment changed: <names>; list only verifier-relevant variables in .specadoc.json verification.environment` | Переменная окружения изменилась между сессиями, поэтому доказательства устарели | Добавьте `verification.environment` в `.specadoc.json`. См. [Конфигурация](../reference/config.md) |

## pre-review и область ревью

| Сообщение | Причина | Исправление |
|---|---|---|
| `no tidy pass recorded (.specadoc.json review.tidy: required)` | Проекту нужен проход tidy перед первым ревью | Запустите `tidy <slug>` и передайте бриф одному worker. Затем запустите `refresh <slug>` |
| `tidy skill not installed at <path>` | Скилла `tidy` нет рядом с папкой `specadoc` | Установите `tidy` в ту же папку скиллов или запустите `tidy <slug> --skip '<reason>'` |
| `files added during apply are missing from Review scope` | Новых файлов нет в `## Review scope` | Запустите `scope <slug>`, затем `pre-review` |
| `line <n>: Review scope lists a Specadoc artifact: <path>; ...` | `## Review scope` называет файл из папки изменения | Удалите эту строку. Область ревью содержит только исполняемый дифф |
| `line <n>: Review scope file does not exist: <path>` | Файл из списка удалён или переименован | Запустите `scope <slug>`. Удалённый файл записывается как `` `!path` `` |
| `Review result: <n> new-diff review rounds recorded; add a **Round cap override:** reason to the latest round, or stop and ask whether to consolidate or split the change` | Три раунда `initial` пройдены | Спросите пользователя. Передайте его решение через `--review-decision` или разделите изменение |

## Устаревший снимок ревью

Раунд ревью хранит манифест хешей файлов из `## Review scope` и контракта спецификации. Если один из них изменился, вердикт уже не покрывает текущий дифф.

| Сообщение | Причина | Исправление |
|---|---|---|
| `<G> recorded FAIL against a stale snapshot (content changed: ...); a stale round uses no review allowance; ...` | Код изменился, пока reviewer работал | Исправьте `## Review scope`. Затем запустите `pre-review --review-type re-review` |
| `<G> recorded FAIL against a stale snapshot (approval or review policy changed ...)` | Одобрение изменилось во время раунда | Доведите одобрение до конца. Снова запустите раунд того же типа на том же диффе |
| `Review result: diff changed since <G>'s snapshot (changed=[...], added=[...], removed=[...]); return to apply for a new review` | Код изменился после PASS (финальный гейт или архивация) | Вернитесь в `apply` и запустите новый раунд ревью |
| `Review result: diff changed since <G>'s snapshot (...); run pre-review --review-type re-review --reason minor-fixes for the executable MINOR fixes` | Исправления MINOR в исполняемом коде после PASS | Запустите это повторное ревью |

Устаревший раунд не входит в лимит раундов. Если PASS был только с замечаниями MINOR, изменение только в тестах или тексте после него сохраняет PASS. Гейт выводит предупреждение и просит назвать эти исправления в `## Archive summary`.

## finalize

| Сообщение | Причина | Исправление |
|---|---|---|
| `result: CHECKED` с `left to the controller: ...` | У некоторых пунктов нет записанного доказательства | Запустите команды, которые называет `next`. Не редактируйте `plan.md` вручную |
| `rows still Pending: <R>; finalize <slug> --requirements '<the evidence that proves them>'` | В матрице требований и проверок есть открытые строки | Запустите `finalize` с `--requirements` |
| `.specadoc.json sets no verification.final` | У `--run` нет команд для запуска | Запустите полный набор тестов сами. Запишите результат через `finalize <slug> --observed '<command, result>'` |
| `the whole suite runs once over accepted code; ...` | Задача ещё не принята | Сначала запустите `accept` или `refresh`, затем `finalize --run` |
| результат `FAIL` с `` `<command>` exit <code> `` | Команда из `verification.final` завершилась с ошибкой | Исправьте ошибку. Исправления исполняемого кода делает worker. Затем снова запустите `finalize --run` |

## Привязки ролей

Specadoc не хранит одобрение привязки. При каждой отправке задачи Specadoc заново читает файлы ролей и `.specadoc.json`, поэтому изменённый файл роли действует со следующей отправки. Строка `Bindings shown` в `plan.md` записывает, что вы видели при одобрении. Последующая правка файла роли не требует нового одобрения.

Эти ошибки появляются, когда проект использует маршрутизацию (`.specadoc.json` с `roles`) или когда контроллер передаёт `--controller-runtime`:

| Сообщение | Причина | Исправление |
|---|---|---|
| `controller runtime is <x>, binding expects <y>; restart in <y> or edit .specadoc.json` | Сессия работает не на том рантайме, который указан в `roles.controller.runtime` | Запустите контроллер на `<y>` или измените `.specadoc.json` |
| `no valid <runtime>/<role> model/effort binding; install a target role file` | У целевого рантайма нет файла роли с моделью и уровнем усилий | Добавьте файл роли в `.claude/agents/`, `.codex/agents/` или `.opencode/agents/` |
| `routed dispatch requires --controller-runtime or roles.controller.runtime` | Проект маршрутизирует роли, но рантайм контроллера неизвестен | Передайте `--controller-runtime` или задайте `roles.controller.runtime` |
| `<path>: wrapper points to <x>, not <y>; migrate to native roles` | Файл устаревшей роли-обёртки расходится с `.specadoc.json` | Замените обёртку файлом нативной роли |

Чтобы посмотреть привязки, запустите `python3 <skill-root>/scripts/role_routing.py --controller-runtime <runtime> --change <slug> --dry-run --compact --check-cli`. См. [Маршрутизация](routing.md).

## Слишком большой план

Это предупреждения. Ни гейт, ни worker, ни шаг архивации их не ждёт.

- `plan.md is <n> bytes (> 49152): keep only decisions, tasks, one-line evidence and current state; ...`. Предупреждение называет четыре самые большие части. Перенесите длинные доказательства в `research.md` или удалите их.
- `plan.md Handoff is <n> bytes (> 2048): ...`. Оставьте в `## Handoff` контрольную точку и одну строку `Continue`. Заметки сессии запишите в `runs/handoff.md` командой `specadoc_step.py handoff`.
- `<n> tasks: inspect change size and dependency boundaries; ...`. В плане больше восьми задач. Исправляющие задачи оставляйте новыми задачами. Не сливайте их с завершёнными задачами.

## Нет reviewer

Контроллер никогда не проверяет свой собственный дифф. Если ни один субагент не может запуститься, контроллер всё равно может выполнять работу scout и worker. Он сообщает, что гейт ревью не завершён, и останавливается, прежде чем заявить о завершении или выполнить обычную архивацию.

Установите или разрешите роль reviewer. Затем снова запустите `pre-review`. См. [Роли](../concepts/roles.md).

| Сообщение | Причина | Исправление |
|---|---|---|
| `record a pending round and manifest before review dispatch` | `review-result` запустили до `pre-review` | Запустите `pre-review <slug>`, затем запустите reviewer |
| `agent <id> already reviewed an earlier round; dispatch a fresh reviewer or pass --same-reviewer-reason` | Тот же агент reviewer получил второй раунд | Запустите нового агента reviewer |
| `invalid reviewer result: <errors>` | В ответе нет корректного JSON с результатом | Запустите reviewer снова. Не копируйте и не редактируйте его ответ |
| `reviewer PASS contradicts open BLOCKER/IMPORTANT findings` | Вердикт противоречит замечаниям. Раунд остаётся открытым | Запустите нового reviewer для открытого раунда |
| `reviewer process did not exit successfully` | Внешний запуск reviewer завершился с ошибкой | Прочитайте его файл запуска. Затем снова запустите reviewer |

## Отказы архивации

| Сообщение | Причина | Исправление |
|---|---|---|
| `error: refusing to archive <slug>: <n> unmet condition(s)` | Гейты открыты. Строки ниже перечисляют каждый из них | Исправьте каждое указанное условие. Снова запустите `--dry-run` |
| `<path>:1: provenance table does not record <slug>` | У спецификации возможности нет строки для этого изменения | Добавьте строку происхождения в эту спецификацию возможности |
| `<path>:1: declared capability file does not exist` | `spec.md` называет спецификацию возможности, которой нет | Создайте её из `assets/capability-template.md` |

`--force` обходит гейты жизненного цикла. Используйте его только по явной просьбе пользователя. Сначала покажите `--force --dry-run`.
