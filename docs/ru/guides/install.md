<!-- source-sha256: e3c9052802a2fbf3da97013bcab964370556c1c81db2a661ab85247cdfbfcdd0 -->
# Установка Specadoc

[English](../../en/guides/install.md)

Specadoc — один плагин с шестью скиллами: `specadoc` и пять необязательных скиллов. Установить его можно тремя способами:

| Хост | Способ | Имя скилла |
|---|---|---|
| Claude Code | плагин из маркетплейса | `specadoc:specadoc` |
| Codex | плагин из локального маркетплейса | `specadoc:specadoc` |
| Codex CLI, OpenCode | обычные папки скиллов | `specadoc` |

Версия плагина 0.1.1. Specadoc не нужны MCP-сервер, аутентификация и хуки жизненного цикла. Установка не меняет конфигурацию хоста и не записывает файлы агентов в ваш проект.

## Требования

- Python 3.10 или новее в `PATH`. Плагин не устанавливает Python.
- Python 3.11 или новее, если в проекте есть файлы ролей Codex (`.codex/agents/<role>.toml`). Specadoc читает эти TOML-файлы модулем `tomllib`, который появился в Python 3.11.
- Git в проекте. Шаг `scope` считает дифф относительно `HEAD`.

Скрипты используют только стандартную библиотеку Python. Каждый скрипт жизненного цикла сначала проверяет версию. На старом интерпретаторе скрипт останавливается с таким сообщением:

```text
error: Specadoc scripts need Python 3.10+; this is 3.9.6 at /usr/bin/python3. Put a newer python3 first on PATH (a terminal started without your login PATH) or call it explicitly.
```

`run_role.py` запускает роль на другом рантайме и использует `fcntl`. Поэтому он не работает в Windows. Остальные скрипты в Windows не тестировали.

## Исходный код

Клонируйте репозиторий один раз. Все способы установки ниже используют эту рабочую копию.

```bash
git clone https://github.com/andreipan/specadoc
```

В этом руководстве `<repo>` — абсолютный путь к рабочей копии.

## Плагин Claude Code

1. Добавьте репозиторий как маркетплейс:

   ```bash
   claude plugin marketplace add <repo>
   ```

   Вместо локального пути команда принимает и Git URL.

2. Установите плагин:

   ```bash
   claude plugin install specadoc@specadoc
   ```

3. Начните новую сессию Claude Code.

Плагин добавляет такие имена:

- Скилл `/specadoc:specadoc`. Режим укажите после имени, например `/specadoc:specadoc explore <request>`.
- Роли `specadoc:scout`, `specadoc:worker` и `specadoc:reviewer`.
- Остальные скиллы в виде `specadoc:<name>`, например `specadoc:tidy`.

Скилл загружается, только когда задача подходит под его описание. Скилл `specadoc` запускается, только когда вы называете его.

Чтобы попробовать плагин на одну сессию без установки, загрузите его из рабочей копии:

```bash
claude --plugin-dir <repo>
```

## Плагин Codex

В рабочей копии есть манифест плагина (`plugin.json`) и файл локального маркетплейса (`.agents/plugins/marketplace.json`). Плагин устанавливает все шесть скиллов.

1. Добавьте рабочую копию как маркетплейс. Укажите абсолютный путь.

   ```bash
   codex plugin marketplace add <repo>
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
6. Назовите режим: `explore`, `propose`, `apply`, `light` или `archive`.

После добавления маркетплейса Specadoc можно также выбрать в каталоге плагинов десктопного приложения.

У скилла `specadoc` задано `allow_implicit_invocation: false`. Codex не запускает его сам. Для остальных скиллов действуют их собственные правила обнаружения.

Codex запускает скиллы из своей установленной копии в кеше, а не из вашей рабочей копии. Не устанавливайте плагин в проект, где уже есть ссылки на те же скиллы или их копии.

Сборка пакета, офлайн-пилот и отдельный `CODEX_HOME` описаны в разделе [Упаковка](../maintainers/packaging.md).

## Обычные скиллы для Codex CLI и OpenCode

Оба хоста читают папки Agent Skills. Сделайте ссылку на папку каждого скилла в проекте или скопируйте её туда.

1. Сделайте ссылку на скилл `specadoc`:

   ```bash
   # Codex
   ln -s <repo>/skills/specadoc <project>/.agents/skills/specadoc
   # OpenCode
   ln -s <repo>/skills/specadoc <project>/.opencode/skills/specadoc
   ```

2. В той же папке сделайте ссылку на каждый нужный необязательный скилл. Подробности в следующем разделе.
3. Начните новую сессию.
4. Назовите скилл по обычному имени, `specadoc`, и режим.

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

1. Если вы добавили маркетплейс из локального пути, загрузите новую версию в рабочую копию.
2. Обновите маркетплейс и плагин:

   ```bash
   claude plugin marketplace update specadoc
   claude plugin update specadoc@specadoc
   ```

3. Перезапустите Claude Code. Обновление вступает в силу только после перезапуска.

### Плагин Codex

`codex plugin marketplace upgrade` обновляет только Git-маркетплейсы. Локальную папку команда не обновляет.

1. Загрузите новую версию в рабочую копию.
2. Удалите плагин и добавьте его снова:

   ```bash
   codex plugin remove specadoc@specadoc
   codex plugin add specadoc@specadoc
   ```

3. Начните новый чат.

### Обычные скиллы

- Если вы сделали ссылки на папки, загрузите новую версию в рабочую копию.
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
