# Публикация DekstopShot на GitHub

Репозиторий: https://github.com/fobesyka-beep/DekstopShot.

Все команды ниже выполняются в **PowerShell**. Исходники отправляются в Git, готовая программа — в **Releases** как ZIP всей папки. Ветки: `main` — стабильная версия, `develop` — разработка. Команды публикации выполняет владелец репозитория; подготовка этих файлов ничего на GitHub не отправляет.

## 1. GitHub CLI и вход

Git уже установлен на текущем компьютере. Установите GitHub CLI:

```powershell
winget install --id GitHub.cli --exact --source winget
```

Если `winget` не найден (в текущем окружении его тоже нет в PATH), вместо этого скачайте официальный MSI GitHub CLI и пройдите установку:

```powershell
$cliRelease = Invoke-RestMethod 'https://api.github.com/repos/cli/cli/releases/latest'
$cliAssets = @($cliRelease.assets | Where-Object { $_.name -match '^gh_[0-9.]+_windows_amd64\.msi$' })
if ($cliAssets.Count -ne 1) { throw 'Не найден официальный установщик GitHub CLI для Windows x64.' }
$cliInstallerPath = Join-Path $env:TEMP 'GitHubCLI-amd64.msi'
Invoke-WebRequest -UseBasicParsing -Uri $cliAssets[0].browser_download_url -OutFile $cliInstallerPath
Start-Process -FilePath $cliInstallerPath -Wait
```

Исходная страница загрузки: [GitHub CLI Releases](https://github.com/cli/cli/releases/latest).

После установки откройте **новый PowerShell**:

```powershell
Set-Location 'C:\Users\danbalyk\PycharmProjects\DekstopShot'
git --version
gh --version
gh auth login --hostname github.com --git-protocol https --web --scopes workflow
gh auth setup-git
gh repo view fobesyka-beep/DekstopShot
```

На момент подготовки документа репозиторий вернул 404 текущему подключению. Это может означать отсутствие доступа к приватному репозиторию или отсутствие самого репозитория. Если после входа под нужным аккаунтом репозиторий действительно ещё не создан:

```powershell
gh repo create fobesyka-beep/DekstopShot --public --description 'Windows screenshot tool with Liquid Glass UI, global hotkeys and clipboard support. Python / PySide6.'
```

Если репозиторий уже существует, пропустите `repo create`. Для индексации Google он должен быть публичным; видимость существующего приватного репозитория меняйте осознанно в его настройках.

## 2. Первый локальный коммит

В текущей рабочей папке `.git` ещё нет. Этот блок предназначен для первого запуска:

```powershell
Set-Location 'C:\Users\danbalyk\PycharmProjects\DekstopShot'
git init -b main
$githubIdentity = gh api user | ConvertFrom-Json
git config user.name $githubIdentity.login
git config user.email "$($githubIdentity.id)+$($githubIdentity.login)@users.noreply.github.com"
git add .
git status --short
git commit -m 'feat: publish DekstopShot Windows screenshot app'
git remote add origin https://github.com/fobesyka-beep/DekstopShot.git
```

`.gitignore` исключает окружения Python, IDE, сборки, локальные проверки, журналы, `.env` и `release`. Иконка, превью, исходники, лицензии и workflow попадут в репозиторий. `git status --short` позволяет просмотреть подготовленные файлы перед коммитом.

## 3. Сохранить существующую историю GitHub и отправить main

Если GitHub уже создал начальный README или LICENSE, сначала объедините историю. Не используйте force push.

```powershell
git fetch origin
if ($LASTEXITCODE -ne 0) { throw 'Не удалось прочитать репозиторий: проверьте URL и доступ.' }

$existingMain = git for-each-ref --format='%(refname)' refs/remotes/origin/main
$existingMaster = git for-each-ref --format='%(refname)' refs/remotes/origin/master
if ($existingMain) {
    git merge origin/main --allow-unrelated-histories --no-edit
    if ($LASTEXITCODE -ne 0) { throw 'Разрешите конфликты, затем продолжите по инструкции ниже.' }
} elseif ($existingMaster) {
    git merge origin/master --allow-unrelated-histories --no-edit
    if ($LASTEXITCODE -ne 0) { throw 'Разрешите конфликты, затем продолжите по инструкции ниже.' }
}

git push -u origin main
```

Если слияние остановилось, посмотрите `git status`, отредактируйте конфликтующие файлы и выполните `git add` / `git commit`. Если конфликтует только README и нужна именно подготовленная локальная версия:

```powershell
git restore --ours --worktree README.md
git add README.md
git commit -m 'Merge existing GitHub history'
git push -u origin main
```

При конфликтах в других файлах сначала разрешите и добавьте их тоже. Не выполняйте следующий блок до завершения слияния.

## 4. Создать develop

Для нового репозитория:

```powershell
git switch -c develop
git push -u origin develop
git switch main
gh repo edit fobesyka-beep/DekstopShot --default-branch main
```

Если `origin/develop` уже существует, вместо создания ветки с нуля:

```powershell
git switch -c develop --track origin/develop
git merge main --no-edit
if ($LASTEXITCODE -ne 0) { throw 'Разрешите конфликты перед push.' }
git push -u origin develop
git switch main
```

Если `develop` уже есть локально, используйте `git switch develop`.

## 5. Описание и topics для поиска

```powershell
gh repo edit fobesyka-beep/DekstopShot `
  --description 'Windows screenshot tool with Liquid Glass UI, global hotkeys, monitor/window capture and clipboard support. Python / PySide6.' `
  --add-topic windows `
  --add-topic screenshot `
  --add-topic clipboard `
  --add-topic global-hotkey `
  --add-topic multi-monitor `
  --add-topic liquid-glass `
  --add-topic python `
  --add-topic pyside6 `
  --add-topic desktop-app
```

README содержит название, описание и реальные функции на русском и английском. Подходящие запросы: «DekstopShot», «скриншот в буфер обмена Windows», «Windows screenshot tool global hotkey», «Liquid Glass screenshot app».

Публичность, содержательный README, описание и внешние ссылки помогают обнаружить проект. Добавление topics или ключевых слов не гарантирует попадание в Google, сроки или высокую позицию. В чужом домене `github.com` нельзя управлять его HTML meta-тегами или подтверждать владение всем доменом в Search Console. Для отдельного собственного сайта можно позже использовать Search Console и sitemap. См. [Google SEO Starter Guide](https://developers.google.com/search/docs/fundamentals/seo-starter-guide) и [требования к индексации](https://developers.google.com/search/docs/essentials/technical).

## 6. Первый Release с готовым приложением

Workflow `.github/workflows/windows-build.yml` выполняет Ruff, тесты и Windows-сборку на push/PR в `main` и `develop`. При отправке тега `v*` он дополнительно создаёт **GitHub Release** с файлами:

- `DekstopShot-Windows-x64.zip` — полная папка приложения, включая `_internal`;
- `SHA256SUMS.txt` — контрольная сумма ZIP.

Публикация исходников в main/develop сама по себе не выпускает новую версию. Для первого выпуска:

```powershell
git switch main
git pull --ff-only origin main
git tag -a v1.0.0 -m 'DekstopShot 1.0.0'
git push origin v1.0.0
gh run list --repo fobesyka-beep/DekstopShot --workflow windows-build.yml --limit 5
gh run watch --repo fobesyka-beep/DekstopShot --exit-status
gh release view v1.0.0 --repo fobesyka-beep/DekstopShot --web
```

`run watch` предложит выбрать запущенную сборку: выберите запуск для тега `v1.0.0`, а не соседние проверки main/develop. Если workflow ещё не появился, обновите список через несколько секунд. Actions должны быть включены в настройках репозитория. Workflow использует встроенный `GITHUB_TOKEN`: отдельный PAT для Releases не требуется. Запуск workflow и публикация на GitHub пока не проверялись; локальная Windows-сборка проверена отдельно в [VALIDATION.md](../VALIDATION.md).

Тег `v1.0.0` отправляйте один раз. Для следующего выпуска используйте новую версию, например `v1.0.1`, и обновляйте версию проекта вместе с изменениями. Если существующий Release требуется отредактировать, открывайте его на GitHub, а не передвигайте уже опубликованный тег.

GitHub автоматически добавит архивы **Source code**. Для запуска приложения скачивать нужно наш `DekstopShot-Windows-x64.zip`, распаковывать его целиком и запускать `DekstopShot.exe` внутри папки.

## 7. Подготовить ZIP локально или прикрепить его вручную

Последняя локальная сборка уже лежит в `dist\DekstopShot`. Упаковка без пересборки:

```powershell
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File .\tools\package_release.ps1
```

Для новой сборки:

```powershell
.\Build_EXE.cmd
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File .\tools\package_release.ps1
Get-FileHash .\release\DekstopShot-Windows-x64.zip -Algorithm SHA256
```

Результат находится в `release`. Скрипт обновляет вложенную документацию и упаковывает всю папку; один exe отдельно неработоспособен.

Если Release уже создан вручную и этих файлов в нём ещё нет, их можно прикрепить командой:

```powershell
gh release upload v1.0.0 `
  .\release\DekstopShot-Windows-x64.zip .\release\SHA256SUMS.txt `
  --repo fobesyka-beep/DekstopShot
```

При успешной автоматической публикации из предыдущего раздела эта команда не нужна. Существующие файлы с такими именами она не перезаписывает.

## 8. Дальнейшая разработка

```powershell
git switch develop
git pull --ff-only origin develop
# Внесите изменения.
git add .
git commit -m 'feat: describe your change'
git push
gh pr create --repo fobesyka-beep/DekstopShot --base main --head develop `
  --title 'Release: describe your change' `
  --body 'Merge the tested development changes into main.'
```

После проверки и слияния PR обновите `main` и создайте новый тег по разделу Releases. Планы английского интерфейса, ProxyAPI и автоматической отправки AI-ответов в Telegram перечислены в [README.md](../README.md); в текущую версию эти интеграции не входят.

Документация GitHub: [описание и topics через gh](https://cli.github.com/manual/gh_repo_edit), [создание Release](https://cli.github.com/manual/gh_release_create), [загрузка файлов](https://cli.github.com/manual/gh_release_upload).
