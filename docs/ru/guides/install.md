<!-- source-sha256: 4ce9e7825f1ae7320ff12ba1ea93a42a819ec99621efe02990634768f8f8fef5 -->
# Установка Specadoc

[English](../../en/guides/install.md)

Specadoc — один плагин с шестью скиллами: `specadoc` и пять необязательных скиллов. Установить его можно тремя способами:

| Хост | Способ | Имя скилла |
|---|---|---|
| Claude Code | плагин из маркетплейса на GitHub | `specadoc:specadoc` |
| Codex | плагин из маркетплейса на GitHub | `specadoc:specadoc` |
| Codex CLI, OpenCode | обычные папки скиллов | `specadoc` |

Версия плагина указана в `plugin.json`. Specadoc не нужны MCP-сервер, аутентификация и хуки жизненного цикла. Установка не меняет конфигурацию хоста и не записывает файлы агентов в ваш проект.

## Требования

- Python 3.10 или новее в `PATH`. Плагин не устанавливает Python.
- Python 3.11 или новее, если в проекте есть файлы ролей Codex (`.codex/agents/<role>.toml`). Specadoc читает эти TOML-файлы модулем `tomllib`, который появился в Python 3.11.
- Git в проекте. Шаг `scope` считает дифф относительно `HEAD`.

Скрипты используют только стандартную библиотеку Python. Каждый скрипт жизненного цикла сначала проверяет версию. На старом интерпретаторе скрипт останавливается с таким сообщением:

```text
error: Specadoc scripts need Python 3.10+; this is 3.9.6 at /usr/bin/python3. Put a newer python3 first on PATH (a terminal started without your login PATH) or call it explicitly.
```

`run_role.py` запускает роль на другом рантайме и использует `fcntl`. Поэтому он не работает в Windows. Остальные скрипты в Windows не тестировали.

## Выбор версии

Репозиторий `andreipan/specadoc` на GitHub одновременно служит маркетплейсом плагина для Claude Code и Codex. Для установки плагина клонировать его не нужно.

- Без тега маркетплейс следует за веткой `main`.
- С тегом релиза маркетплейс остаётся на этом релизе. Теги перечислены на [странице релизов](https://github.com/andreipan/specadoc/releases). В примерах ниже тег обозначен как `<tag>`, например `v0.1.4`.

Для командных проектов рекомендуем тег: тогда все участники работают с одной версией.

## Плагин Claude Code

1. Добавьте маркетплейс одной из команд:

   ```bash
   claude plugin marketplace add andreipan/specadoc          # follows main
   claude plugin marketplace add andreipan/specadoc@<tag>    # stays on a release
   ```

2. Установите плагин:

   ```bash
   claude plugin install specadoc@specadoc
   ```

3. Начните новую сессию Claude Code.

Плагин даёт такие имена:

- Скилл `/specadoc:specadoc`. После него укажите режим, например `/specadoc:specadoc explore <request>`.
- Роли `specadoc:scout`, `specadoc:worker` и `specadoc:reviewer`.
- Остальные скиллы как `specadoc:<name>`, например `specadoc:tidy`.

Скилл загружается, только когда задача подходит под его описание. Скилл `specadoc` запускается, только когда вы называете его.

### Плагин для команды

Чтобы объявить маркетплейс для проекта, добавьте `--scope project` к команде `marketplace add`. Тогда Claude Code запишет маркетплейс в `.claude/settings.json` проекта. Закоммитьте этот файл.

Участник команды получает маркетплейс, когда подтверждает доверие к папке проекта. Затем каждый участник устанавливает плагин:

```bash
claude plugin install specadoc@specadoc --scope project
```

### Плагин без установки

Чтобы загрузить плагин только на одну сессию, клонируйте репозиторий и укажите его путь:

```bash
git clone https://github.com/andreipan/specadoc
claude --plugin-dir <repo>
```

`<repo>` — абсолютный путь к клону.

## Плагин Codex

1. Добавьте маркетплейс одной из команд:

   ```bash
   codex plugin marketplace add andreipan/specadoc               # follows main
   codex plugin marketplace add andreipan/specadoc --ref <tag>   # stays on a release
   ```

2. Установите плагин:

   ```bash
   codex plugin add specadoc@specadoc
   ```

3. Проверьте, что плагин есть в списке:

   ```bash
   codex plugin list
   ```

4. Начните новый чат.
5. Выберите скилл `specadoc:specadoc`. Если хост это поддерживает, введите `$specadoc:specadoc`.
6. Укажите режим: `explore`, `propose`, `apply`, `light` или `archive`.

Плагин устанавливает все шесть скиллов. После добавления маркетплейса Specadoc можно также выбрать в каталоге плагинов десктопного приложения.

У скилла `specadoc` указано `allow_implicit_invocation: false`. Codex не запускает его сам. Остальные скиллы сохраняют свои правила обнаружения.

Codex запускает скиллы из своей установленной копии в кеше. Не устанавливайте плагин в проект, где уже есть ссылки на те же скиллы или их копии.

Об упаковке, офлайн-пилоте и отдельном `CODEX_HOME` см. [Упаковка и релиз](../maintainers/packaging.md).

## Обычные скиллы для Codex CLI и OpenCode

Оба хоста читают папки Agent Skills. Сделайте ссылку на папку каждого скилла в проекте или скопируйте её туда.

1. Клонируйте репозиторий. Чтобы остаться на релизе, переключитесь на его тег:

   ```bash
   git clone https://github.com/andreipan/specadoc
   git -C specadoc checkout <tag>
   ```

   В командах ниже `<repo>` — абсолютный путь к клону.

2. Сделайте ссылку на скилл `specadoc`:

   ```bash
   # Codex
   ln -s <repo>/skills/specadoc <project>/.agents/skills/specadoc
   # OpenCode
   ln -s <repo>/skills/specadoc <project>/.opencode/skills/specadoc
   ```

3. В той же папке сделайте ссылку на каждый нужный необязательный скилл. Подробности в следующем разделе.
4. Начните новую сессию.
5. Назовите скилл по обычному имени, `specadoc`, и режим.

Для этих хостов Specadoc не записывает конфигурацию агентов. Если у проекта есть свои роли (`.codex/agents/<role>.toml` или `.opencode/agents/<role>.md`), Specadoc использует их. Иначе контроллер передаёт доступному субагенту переносимый контракт роли из `skills/specadoc/references/roles/`. Полный порядок описан на странице [Роли](../concepts/roles.md).

## Сопутствующие скиллы

В репозитории есть ещё пять скиллов в `skills/`. Каждый скилл работает без Specadoc.

| Скилл | Вид | Назначение |
|---|---|---|
| `tidy` | сопутствующий скилл | Чистка кода без изменения поведения перед финальным ревью |
| `codebase-design` | сопутствующий скилл | Решение контроллера по нерешённому интерфейсу или шву |
| `domain-modeling` | сопутствующий скилл | Неоднозначные термины, состояния и инварианты при уточнении требований |
| `foreman` | управляющий скилл | Один постоянный исполнитель под основной сессией |
| `orchestrator` | управляющий скилл | Несколько контроллеров Specadoc для одного результата |

Плагины Claude Code и Codex устанавливают все пять. Для обычных скиллов сделайте ссылки только на те скиллы, которые нужны проекту:

```bash
ln -s <repo>/skills/tidy <project>/.agents/skills/tidy
```

Положите `tidy` в ту же папку, что и `specadoc`. Шаг `specadoc_step.py tidy` ищет `tidy/SKILL.md` рядом с папкой `specadoc`. Если файла там нет, шаг останавливается с сообщением `tidy skill not installed at <path>`.

Скилла `grilling` в этом репозитории нет. Specadoc использует его в explore и propose, если он есть у хоста. Установите его обычным для вашего хоста способом.

Когда использовать каждый скилл, описано на страницах [Сопутствующие скиллы](companion-skills.md) и [Orchestrator и foreman](orchestrator-and-foreman.md).

## Проверка установки

В справочных страницах `<skill-root>` — установленная папка `skills/specadoc`. В Claude Code агент видит эту папку как `${CLAUDE_SKILL_DIR}`. Для обычного скилла это папка, на которую вы сделали ссылку.

1. Перейдите в корень репозитория проекта.
2. Запустите doctor:

   ```bash
   python3 <skill-root>/scripts/doctor.py
   ```

   Doctor только читает файлы. В проекте без файлов Specadoc он выводит:

   ```text
   root: docs/specadoc (default)
   capability specs: 0
   archive records: 0
   Specadoc doctor: no findings.
   ```

3. Если doctor остановился с ошибкой версии Python, поставьте Python 3.10 или новее первым в `PATH`. Затем запустите doctor снова.
4. Начните новую сессию и попросите агента: `specadoc explore <a small question about this repository>`. Explore не записывает файлы, поэтому эта проверка безопасна.

Если в проекте есть `.specadoc.json` с `roles`, также запустите `python3 <skill-root>/scripts/doctor.py --controller-runtime <claude|codex|opencode>`. Эта команда проверяет маршрутизацию ролей и наличие CLI каждого рантайма в `PATH`.

Не используйте этот параметр в проекте без `roles`. Без `roles` Specadoc ищет роли в порядке, который описан на странице [Роли](../concepts/roles.md). Проверка маршрутизации читает только файлы ролей проекта. Поэтому она сообщает об ошибках в файлах, которые проекту не нужны. Подробнее на странице [Маршрутизация](routing.md).

## Обновление

Обновление не меняет `.specadoc.json` и ваши файлы ролей.

### Claude Code

Если маркетплейс следует за `main`:

1. Обновите маркетплейс и плагин:

   ```bash
   claude plugin marketplace update specadoc
   claude plugin update specadoc@specadoc
   ```

2. Перезапустите Claude Code. Обновление вступает в силу только после перезапуска.

Новый релиз приходит, только когда меняется его версия в `plugin.json`.

Чтобы перейти на другой тег релиза, добавьте маркетплейс заново. Команда `marketplace remove` удаляет и плагин, поэтому установите его снова:

```bash
claude plugin marketplace remove specadoc
claude plugin marketplace add andreipan/specadoc@<tag>
claude plugin install specadoc@specadoc
```

### Плагин Codex

Если маркетплейс следует за `main`:

1. Обновите маркетплейс:

   ```bash
   codex plugin marketplace upgrade specadoc
   ```

2. Удалите плагин и добавьте его снова:

   ```bash
   codex plugin remove specadoc@specadoc
   codex plugin add specadoc@specadoc
   ```

3. Начните новый чат.

Чтобы перейти на другой тег релиза, добавьте маркетплейс заново с новым тегом. Затем удалите плагин и добавьте его снова. Без переустановки Codex оставляет старую версию.

```bash
codex plugin marketplace remove specadoc
codex plugin marketplace add andreipan/specadoc --ref <tag>
codex plugin remove specadoc@specadoc
codex plugin add specadoc@specadoc
```

### Обычные скиллы

- Если вы сделали ссылки на папки, выполните `git pull` в клоне или переключитесь на новый тег.
- Если вы скопировали папки, скопируйте их снова.

После обновления начните новую сессию.

## Удаление

Удаление плагина не удаляет `docs/specadoc/` из ваших проектов. Спецификации, планы и архивные записи остаются в репозитории.

Claude Code:

```bash
claude plugin uninstall specadoc@specadoc
claude plugin marketplace remove specadoc
```

Плагин Codex:

```bash
codex plugin remove specadoc@specadoc
codex plugin marketplace remove specadoc
```

Обычные скиллы: удалите ссылки или скопированные папки из `.agents/skills/` или `.opencode/skills/`.
