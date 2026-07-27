# Tankarta pro Home Assistant

Vlastní HACS integrace pro přihlášení do portálu `business.tankarta.cz` a vytvoření cenových senzorů z JSON endpointu:

```text
https://business.tankarta.cz/Dashboard-ListPrice
```

Integrace navazuje na stejný model jako INMES: Home Assistant neposílá Playwright jako Python závislost, ale spouští přihlášení a načtení JSON přes existující Browserless Chromium.

## Vytvářené entity

Pro každý produkt vrácený endpointem vznikne dynamický peněžní senzor, například:

- `sensor.tankarta_verva_100`
- `sensor.tankarta_verva_diesel`
- `sensor.tankarta_adblue`
- `sensor.tankarta_efecta_95`
- `sensor.tankarta_efecta_diesel`
- `sensor.tankarta_h2`
- `sensor.tankarta_hvo100_diesel`

Přesný `entity_id` přiděluje Home Assistant a může se po přejmenování lišit.

Dále integrace vytvoří:

- senzor **Poslední aktualizace**,
- tlačítko **Obnovit ceny**.

Nový produkt se po dalším načtení přidá automaticky. Produkt, který z odpovědi zmizí, zůstane v registru entit, ale bude nedostupný.

## Zacházení s `divisionID`

`divisionID` se nikde ručně nenastavuje. Integrace ho používá pouze během zpracování právě načtené odpovědi, aby dokázala rozlišit dva stejně pojmenované produkty z různých divizí.

- není uložen v config entry,
- není v názvu entity ani zařízení,
- není ve state attributes,
- není zapisován do logu,
- pro interní klíč entity se používá pouze osolený SHA-256 hash,
- surová hodnota po parsování nezůstává v koordinovaných datech.

Pokud endpoint vrátí stejný produkt pro více divizí, názvy budou například `Verva Diesel (varianta 1)` a `Verva Diesel (varianta 2)` bez zveřejnění identifikátoru divize.

## Jednotka ceny

Endpoint vrací pouze `productPrice`, nikoli měnu ani jmenovatel ceny. Integrace proto používá konfigurovatelný třípísmenný kód měny, ve výchozím stavu `CZK`, a nesnaží se tvrdit, zda je konkrétní hodnota za litr, kilogram nebo jinou jednotku.

## Požadavky

- Home Assistant 2026.6 nebo novější,
- Browserless Chromium dostupný z Home Assistantu,
- účet na `business.tankarta.cz` bez povinného jednorázového 2FA při každém přihlášení.

Výchozí URL Browserless:

```text
http://db21ed7f-browserless-chrome:3000
```

Lze vložit také úplnou WebSocket URL z Changedetection. Integrace ji převede na HTTP endpoint `/chromium/function` a zachová parametry dotazu.

## Instalace ručně

Zkopíruj:

```text
custom_components/tankarta
```

do:

```text
/config/custom_components/tankarta
```

Restartuj Home Assistant a otevři:

```text
Nastavení -> Zařízení a služby -> Přidat integraci -> Tankarta
```

## Instalace přes HACS

1. V `custom_components/tankarta/manifest.json` nahraď `REPLACE_ME` svým GitHub účtem nebo organizací.
2. Nahraj celý repozitář na veřejný GitHub.
3. V HACS přidej repozitář jako vlastní repozitář typu **Integration**.
4. Nainstaluj integraci a restartuj Home Assistant.

## Aktualizace

Výchozí interval je 360 minut. Lze jej změnit v:

```text
Nastavení -> Zařízení a služby -> Tankarta -> Konfigurovat
```

Povolený rozsah je 15 až 1440 minut.

## Bezpečnost

Heslo je uloženo v config entry Home Assistantu stejně jako u jiných UI integrací. Cookies a webové úložiště prohlížeče jsou uchovávány pouze v runtime paměti integrace a po restartu Home Assistantu se zahodí.

Integrace úmyslně neloguje:

- uživatelské jméno ani heslo,
- Browserless token,
- cookies, local storage ani session storage,
- `divisionID`,
- obsah neočekávaných HTTP odpovědí.

Dočasné debug logování:

```yaml
logger:
  logs:
    custom_components.tankarta: debug
```

## Omezení

Portál není veřejné API a může změnit přihlašovací formulář nebo endpoint. Config flow při instalaci provede skutečné přihlášení a načtení cen, takže nefunkční selektory nebo změněný JSON zjistí ještě před uložením konfigurace.
