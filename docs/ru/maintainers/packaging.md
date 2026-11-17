<!-- source-sha256: 6da72d7d1fe43aeb7fb1150848b30e684245c4c153b701875153ae4b505ee4e5 -->
# Упаковка и релиз

[English](../../en/maintainers/packaging.md)

Эта страница объясняет мейнтейнерам, как устроены версия плагина, манифесты и
релизный ZIP и как выпустить релиз. Тесты и адаптеры ролей описаны в разделе
[Разработка](development.md).

Релиз только локальный. Мейнтейнер создаёт тег git и ZIP. Никто не загружает
пакет в публичный каталог плагинов и не отправляет его на проверку. Корректный
пакет не означает одобрения публичного каталога.

## Версия и манифесты

В репозитории четыре файла манифеста:

| Файл | Хост | Содержимое |
|---|---|---|
| `plugin.json` | Переносимый пакет, Codex | Имя, версия, описание, автор, лицензия, ключевые слова и интерфейс `com.openai` |
| `.claude-plugin/plugin.json` | Claude Code | Те же имя, версия, описание, автор, лицензия и ключевые слова |
| `.claude-plugin/marketplace.json` | Claude Code | Одна запись плагина, `specadoc`, с источником `./` |
| `.agents/plugins/marketplace.json` | Codex | Одна запись плагина, `specadoc`, с локальным источником `./` |

Версия есть только в двух файлах `plugin.json`. В файлах маркетплейса версии
нет. Имя ZIP строится по версии из `plugin.json`.

`python3 scripts/package_plugin.py --check` отклоняет пакет при таких ошибках:

- У `plugin.json` и `.claude-plugin/plugin.json` разные или пустые `name`,
  `version`, `description`, `author`, `license` или `keywords`.
- Версия не в формате `X.Y.Z`.
- В `plugin.json` значение `$schema` отличается от
  `https://agent-plugins.org/schemas/1.0.0/plugin.schema.json`.
- Расширение `com.openai` объявляет `hooks`, `apps` или `mcpServers`. Пакет
  содержит только скиллы.
- В интерфейсе `com.openai` нет `displayName`, `shortDescription`,
  `developerName` или `category`.
- В `.agents/plugins/marketplace.json` не ровно одна запись `specadoc` с
  источником `{"source": "local", "path": "./"}`, политикой
  `{"installation": "AVAILABLE", "authentication": "ON_USE"}` и категорией
  `Productivity`.

Та же команда проверяет и скиллы:

- В `skills/` ровно шесть папок: `specadoc`, `tidy`, `codebase-design`,
  `domain-modeling`, `foreman` и `orchestrator`.
- Во frontmatter `SKILL.md` каждого скилла есть `name`, равное имени папки, и
  `description`.
- Каждый путь в обратных кавычках, который начинается с `references/`,
  `scripts/`, `assets/` или `roles/`, ведёт к существующему файлу.
- У `skills/specadoc`, `skills/foreman` и `skills/orchestrator` в
  `agents/openai.yaml` задано `allow_implicit_invocation: false`. Эти скиллы
  запускаются только по явному запросу.
- Три переносимых контракта ролей есть в `skills/specadoc/references/roles/`.
- Каждый файл ZIP существует, и среди них нет символических ссылок.

`package_plugin.py` не читает `.claude-plugin/marketplace.json`. Если CLI
`claude` есть в `PATH`, `check.sh` запускает `claude plugin validate . --strict`
для файлов Claude Code.

## Сборка ZIP

Чтобы собрать ZIP, запустите:

```bash
python3 scripts/package_plugin.py
```

Сначала скрипт проверяет пакет. Если проверка прошла, скрипт пишет
`dist/specadoc-<version>.zip` и выводит путь и `sha256:<digest>`. Чтобы записать
ZIP по другому пути, добавьте `--output <path>`. Git игнорирует `dist/`.

### Содержимое ZIP

| В ZIP | Не в ZIP |
|---|---|
| `plugin.json` | `.claude-plugin/` |
| `README.md`, `README.ru.md` | `.agents/` |
| `CHANGELOG.md`, `CHANGELOG.ru.md` | `agents/` (адаптеры Claude Code) |
| `LICENSE`, `THIRD_PARTY_NOTICES.md` | `scripts/` |
| Каждый файл `.md` в `docs/en/` и `docs/ru/` | `tests/` |
| Все файлы шести папок скиллов, включая `evals/` | `.git`, `__pycache__/`, `*.pyc`, `.DS_Store` |

Все файлы из левой колонки должны существовать. Если нет файла верхнего
уровня, `docs/en/` или `docs/ru/`, сборка останавливается с ошибкой.

В ZIP нет файла маркетплейса. Также в ZIP нет манифеста Claude Code и адаптеров
ролей. Claude Code устанавливает плагин из репозитория через
`.claude-plugin/marketplace.json`.

### Детерминированная сборка

Из одного и того же дерева исходников сборка даёт одинаковые байты:

- Записи отсортированы по пути.
- У каждой записи метка времени 1980-01-01 00:00:00 и режим `0644`.
- Все записи сжаты методом deflate с уровнем 9.

`test_plugin_package.py` собирает ZIP два раза и сравнивает байты. Другая версия
Python или zlib может сжимать по-другому. Поэтому сравнивайте дайджесты только
у сборок в одной и той же среде.

## Офлайн-пилот Codex

`scripts/smoke_codex.py` устанавливает собранный пакет в Codex и потом удаляет
его. Пилот запускают только вручную: `check.sh` его не запускает. Нужен CLI
`codex` в `PATH`.

```bash
python3 scripts/smoke_codex.py --report dist/codex-pilot.json
```

Пилот использует временные `HOME` и `CODEX_HOME`. Он удаляет `OPENAI_API_KEY`
и `CODEX_API_KEY` из своего окружения. Он не меняет вашу конфигурацию Codex и
не запускает ход модели. Пилот выполняет такие шаги:

1. Собирает ZIP во временную папку и распаковывает его. Затем добавляет копию
   `.agents/plugins/marketplace.json`.
2. Добавляет маркетплейс и устанавливает `specadoc@specadoc`. Установленная
   копия должна быть внутри временного `CODEX_HOME`.
3. Запускает `codex app-server --stdio` и открывает временный тред. Все шесть
   скиллов должны загрузиться из установленной копии как `specadoc:<name>`.
4. Читает установленные файлы `agents/openai.yaml`. У Specadoc, Foreman и
   Orchestrator должно остаться `allow_implicit_invocation: false`.
5. Запускает `--help` для каждого установленного скрипта Specadoc. Затем
   запускает `init_change.py pilot --no-scout 'pilot change'` во временном проекте.
6. Меняет распакованный источник. Установленная копия должна оставаться прежней
   до удаления и новой установки.
7. Удаляет плагин и маркетплейс. Установленной копии и скиллов больше не должно
   быть.

Скрипт выводит отчёт JSON с полями `checks`, `gaps`, `version`, `client` и
`skills`. С `--report <path>` скрипт также сохраняет отчёт. В отчёте указан
один пробел: в пилоте нет ходов модели и действий в настольном интерфейсе.

## Локальный пилот Codex вручную

Используйте эту процедуру, чтобы проверить рабочую копию в Codex перед релизом.
Используйте отдельный тестовый проект. Укажите в `CODEX_HOME` пустую папку,
чтобы ваша конфигурация Codex не изменилась.

1. Добавьте рабочую копию как маркетплейс:

   ```bash
   codex plugin marketplace add /absolute/path/to/specadoc
   ```

2. Установите плагин:

   ```bash
   codex plugin add specadoc@specadoc
   ```

3. Начните новый чат. Явно выберите скилл `specadoc:specadoc`.

Codex запускает скиллы из своей установленной копии, а не из рабочей копии.
После изменения рабочей копии установите плагин заново:

```bash
codex plugin remove specadoc@specadoc
codex plugin add specadoc@specadoc
```

Затем начните новый чат. `codex plugin marketplace upgrade` обновляет только
источники Git. Локальную папку команда не обновляет.

После пилота удалите плагин и маркетплейс:

```bash
codex plugin remove specadoc@specadoc
codex plugin marketplace remove specadoc
```

Чтобы проверить собранный ZIP вместо рабочей копии, распакуйте ZIP в новую
папку. Скопируйте `.agents/plugins/marketplace.json` из рабочей копии по тому
же пути в эту папку. Затем используйте эту папку в шаге 1.

## Выпуск релиза

Выполните эти шаги из корня репозитория:

1. Задайте новую версию `X.Y.Z` в `plugin.json`.
2. Задайте ту же версию в `.claude-plugin/plugin.json`.
3. В `CHANGELOG.md` перенесите записи из `## [Unreleased]` в новый раздел
   `## [X.Y.Z] - YYYY-MM-DD`.
4. Внесите такую же правку в `CHANGELOG.ru.md`.
5. Укажите пример тега `vX.Y.Z` в `README.md`, `README.ru.md` и в обоих
   руководствах по установке. `tests/test_docs.py` проверяет эти примеры.
6. Запустите `python3 scripts/docs_sync.py --stamp` для каждого изменённого русского файла.
7. Запустите `scripts/check.sh`. Если шаг упал, устраните причину и запустите скрипт снова.
8. Запустите `python3 scripts/package_plugin.py`. Сохраните выведенный дайджест SHA-256.
9. Если CLI `codex` доступен, можно запустить
   `python3 scripts/smoke_codex.py --report dist/codex-pilot.json`.
10. Закоммитьте правки версии и журнала изменений.
11. Создайте аннотированный тег: `git tag -a vX.Y.Z -m "Specadoc X.Y.Z"`.
12. Отправьте ветку и тег: `git push origin main vX.Y.Z`.
13. Создайте релиз на GitHub из тега. В описание возьмите раздел журнала
    изменений и приложите ZIP:
    `gh release create vX.Y.Z dist/specadoc-X.Y.Z.zip --verify-tag --notes-file <notes>`.

Не загружайте ZIP в публичный каталог плагинов. Релиз — это тег и релиз на
GitHub с ZIP.
