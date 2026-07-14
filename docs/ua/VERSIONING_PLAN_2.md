# RobotArmGA — регламент версіонування і відтворюваності
Статус: проект регламенту для обговорення. Дата: 2026-07-09.

## 1. Структура репозиторію (один моно-репозиторій)
Корінь: C:\simulation  →  репозиторій "robot-arm-ga"

```
robot-arm-ga/
├── RobotArmGA/            # Unity-проект (тільки джерела, див. .gitignore)
│   ├── Assets/
│   ├── Packages/
│   └── ProjectSettings/
├── ga-server/             # Python-сервер
│   ├── main.py  ga_engine.py  protocol.py  plot_convergence.py
│   └── requirements.txt   # СТВОРИТИ: pip freeze > requirements.txt
├── docs/                  # проектні документи (ПЕРЕНЕСТИ сюди)
│   ├── DECISIONS.md  GENOME_SPEC.md
│   ├── DISCUSSION_NOTES.md  RESULTS_LOG.md
│   └── runs_index.md      # реєстр прогонів (див. §5)
├── figures/               # фінальні рисунки статті (png/pdf)
│   └── (кожен png має рядок у runs_index: чим згенерований)
├── README.md              # інструкція відтворення (див. §7)
├── LICENSE                # MIT
└── .gitignore
```

## 2. Що трекається git'ом / що НІ
ТАК: увесь код (C#, Python), ProjectSettings, Packages/manifest.json,
документи docs/, README, .gitignore, requirements.txt, фінальні
figures/ (вони маленькі і є частиною статті).

НІ (у .gitignore):
```
RobotArmGA/[Ll]ibrary/    RobotArmGA/[Tt]emp/    RobotArmGA/[Oo]bj/
RobotArmGA/[Bb]uild*/     RobotArmGA/[Ll]ogs/    RobotArmGA/[Uu]serSettings/
*.csproj   *.sln   __pycache__/   *.pyc
ga-server/logs/           # дані прогонів — НЕ в git (див. §4)
```

## 3. Конвенції комітів і тегів
- Гілка одна: main. Гілкування не потрібне для соло-дослідження.
- Коміт: коротке повідомлення "що і навіщо", укр. або англ., одна тема
  на коміт. Приклади: "NSGA-II: недоміноване сортування + crowding",
  "Т11: гени розміщення бази (r, φ)".
- Тег = зафіксована ВЕРСІЯ ПОСТАНОВКИ або СЕРІЇ:
  * v1.1-baseline    — згортка + self-paced curriculum (поточний стан)
  * v2.0-nsga2       — перехід на NSGA-II (+ критерій M, Т9)
  * v2.1-placement   — гени розміщення бази (Т11)
  * series-t10       — код серії уставок {4/25/50}%
  * paper-v1         — рівно той код, що дав рисунки поданої статті
- ЗАЛІЗНЕ ПРАВИЛО: перед стартом будь-якої офіційної серії — commit + tag.

## 4. Дані прогонів (logs/) — окремий контур
- git — для КОДУ; дані великі й незмінні → зберігаються поза git:
  локально ga-server/logs/run_*/ + ДЗЕРКАЛО на зовнішній носій/хмару
  (OneDrive/Drive — тут якраз доречні) після кожної офіційної серії.
- Зв'язка код↔дані: сервер пише в config.json прогону git-хеш коду
  (патч main.py — 3 рядки, додаємо після git init).
- На момент подання статті: логи ОФІЦІЙНИХ серій пакуються в
  zip-датасет і публікуються на Zenodo окремим записом з DOI
  (стаття посилається і на код, і на дані).

## 5. Реєстр прогонів docs/runs_index.md — одна таблиця
| run_id (папка) | дата | тег/хеш коду | сід | постановка | серія/мета | де фігурує |
|---|---|---|---|---|---|---|
| run_20260709_083012 | 09.07 | v1.1-baseline | 42 | v1.1 | B/self-paced | рис. результат_9 |
Правило: рядок додається ОДРАЗУ після завершення прогону (30 секунд).
Це головний документ, який рятує від "а що це за графік" через півроку.

## 6. Віддалені сервіси
1) GitHub, приватний репозиторій — з першого дня (бекап + історія):
   git remote add origin ... ; git push -u origin main --tags
2) На поданні статті:
   - репозиторій → public;
   - GitHub Release з тега paper-v1;
   - Zenodo (zenodo.org, вхід через GitHub) → увімкнути репозиторій →
     реліз автоматично отримує DOI виду 10.5281/zenodo.XXXXXXX;
   - другий Zenodo-запис: датасет логів офіційних серій (окремий DOI).
3) У статті (Data Availability Statement):
   "The source code of the simulation framework and optimization
   server is openly available at Zenodo (DOI: 10.5281/zenodo.XXXX,
   version paper-v1) and GitHub (github.com/...). Raw experimental
   logs for all reported series are available at Zenodo
   (DOI: 10.5281/zenodo.YYYY)."
   Посилання в тексті — ТІЛЬКИ на DOI/тег, ніколи на живий main.

## 7. README.md — обов'язкові розділи
1. Що це (2 абзаци) + скріншот сцени;
2. Вимоги: Unity 6000.3.8f1, Python 3.14, pip install -r requirements.txt;
3. Швидкий старт: запуск сервера → відкрити сцену → налаштування
   інспектора (таблиця значень) → Play → plot_convergence.py;
4. Відтворення рисунків статті: таблиця "рисунок → тег коду → сід →
   команда" (джерело — runs_index.md);
5. Структура репозиторію; 6. Ліцензія MIT; 7. Як цитувати (після DOI).

## 8. Порядок дій (чеклист)
СЬОГОДНІ:
[ ] git init + .gitignore + перший коміт + тег v1.1-baseline
[ ] pip freeze > ga-server/requirements.txt (закомітити)
[ ] перенести 4 md-документи в docs/, створити runs_index.md,
    заднім числом внести відомі прогони (серії A і B)
[ ] GitHub приватний + push
[ ] патч main.py: git-хеш у config.json (роблю я)
[ ] дзеркало наявних logs/ на зовнішній носій/хмару
ПЕРЕД КОЖНОЮ СЕРІЄЮ: [ ] commit + tag  [ ] рядки в runs_index після
НА ПОДАННІ: [ ] реліз paper-v1  [ ] public  [ ] 2×Zenodo DOI
[ ] Data Availability з DOI  [ ] README §4 звірений з рисунками
```
