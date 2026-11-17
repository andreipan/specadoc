<!-- source-sha256: 2af373df59079c25124dcf0b8c3ece5a5bfd5e8d92eee5d92dcb3c6a9c7b304f -->
# Документация Specadoc

[English](../en/index.md)

Это карта документации Specadoc. Для короткого знакомства сначала прочитайте
[README](../../README.ru.md).

Инструкции для агентов лежат в `skills/specadoc/SKILL.md` и
`skills/specadoc/references/`. Эти страницы объясняют ту же систему человеку.
Если страница и скилл расходятся, источник истины — скилл. Сообщите о
расхождении как об ошибке документации.

## С чего начать

| Вам нужно | Читайте |
|---|---|
| Установить Specadoc | [Установка](guides/install.md) |
| Провести первое изменение от начала до конца | [Ваше первое изменение](guides/first-change.md) |
| Выбрать между `light`, `propose` и `explore` | [Light или propose](guides/light-or-propose.md) |
| Исправить отклонённый шаг или непройденный гейт | [Устранение неполадок](guides/troubleshooting.md) |
| Понять, почему Specadoc устроен именно так | [Концепции](#концепции) |
| Найти точное имя флага, ключа или раздела | [Справочник](#справочник) |

## Концепции

- [Жизненный цикл](concepts/lifecycle.md): режимы, как Specadoc выбирает
  режим и как продолжается активное изменение.
- [Роли](concepts/roles.md): контроллер, `scout`, `worker` и `reviewer` и за
  что отвечает каждый из них.
- [Артефакты и гейты](concepts/artifacts-and-gates.md): спецификация, план,
  спецификации возможностей, архивные записи и проверки между фазами.

## Руководства

- [Установка](guides/install.md): Claude Code, Codex и OpenCode.
- [Ваше первое изменение](guides/first-change.md): `propose`, `apply` и
  `archive` на примере.
- [Light или propose](guides/light-or-propose.md): как выбрать подходящий
  режим.
- [Маршрутизация](guides/routing.md): запуск ролей на Claude, Codex или
  OpenCode через `.specadoc.json`.
- [Orchestrator и Foreman](guides/orchestrator-and-foreman.md): длинные
  задачи и несколько контроллеров.
- [Сопутствующие скиллы](guides/companion-skills.md): `tidy`,
  `codebase-design`, `domain-modeling` и `grilling`.
- [Устранение неполадок](guides/troubleshooting.md): типичные отказы и что с
  ними делать.

## Справочник

- [Режимы](reference/modes.md): синтаксис, входные данные, результаты и точки
  остановки.
- [Скрипты](reference/scripts.md): все скрипты, их подкоманды и флаги.
- [Конфигурация](reference/config.md): `.specadoc.json` и корень артефактов.
- [Структура плана](reference/plan-structure.md): разделы `spec.md`,
  `plan.md` и `record.md`.
- [Глоссарий](reference/glossary.md): термины, которые используются на этих
  страницах.

## Для мейнтейнеров

- [Разработка](maintainers/development.md): структура репозитория, тесты и
  контракты ролей.
- [Упаковка и релиз](maintainers/packaging.md): манифесты, релизный ZIP,
  пилотный прогон Codex и теги.
- [CHANGELOG](../../CHANGELOG.ru.md)
