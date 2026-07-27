# Tankarta pro Home Assistant

Vlastní HACS integrace pro přihlášení do portálu `business.tankarta.cz` a vytvoření cenových senzorů z JSON endpointu:

```text
POST https://business.tankarta.cz/Dashboard-ListPrice
```

Integrace používá Browserless Chromium stejně jako předchozí integrace INMES. Home Assistant proto nepotřebuje lokální Python balíček Playwright.

## Důležité: instalace v HACS ještě nevytvoří senzory

HACS pouze stáhne integraci do:

```text
/config/custom_components/tankarta
```

Po instalaci je nutné:

1. restartovat celý Home Assistant,
2. v prohlížeči provést tvrdý refresh (`Ctrl+F5`),
3. otevřít **Nastavení → Zařízení a služby**,
4. zvolit **Přidat integraci**,
5. vyhledat **Tankarta**,
6. dokončit přihlášení a test Browserless.

Teprve úspěšné dokončení config flow vytvoří kartu integrace, zařízení a senzory. Adresa `/config/integrations/dashboard` je stránka uživatelského rozhraní, nikoli adresář v `/config`.

Pokud se Tankarta v dialogu **Přidat integraci** vůbec nenabízí, ověř:

```text
/config/custom_components/tankarta/manifest.json
/config/custom_components/tankarta/config_flow.py
```

a po instalaci znovu restartuj Home Assistant.

## Vytvářené entity

Pro každý produkt vrácený endpointem vznikne dynamický peněžní senzor, například:

- `sensor.tankarta_verva_100`
- `sensor.tankarta_verva_diesel`
- `sensor.tankarta_adblue`
- `sensor.tankarta_efecta_95`
- `sensor.tankarta_efecta_diesel`
- `sensor.tankarta_h2`
- `sensor.tankarta_hvo100_diesel`

Přesný `entity_id` přiděluje Home Assistant a může se lišit.

Dále integrace vytvoří:

- senzor **Poslední aktualizace**,
- tlačítko **Obnovit ceny**.

Nový produkt se po dalším načtení přidá automaticky. Produkt, který z odpovědi zmizí, zůstane v registru entit, ale bude nedostupný.

## Atribut `division_id`

`divisionID` se nikde ručně nenastavuje. Načítá se dynamicky z každé položky JSON a u cenového senzoru je dostupný jako atribut:

```yaml
product: Verva 100
division_id: 123456
```

Surový identifikátor se stále nepoužívá v názvu entity, `entity_id`, `unique_id`, názvu zařízení ani logu. Stabilní interní klíč entity používá osolený SHA-256 hash kombinace produktu a divize.

Pokud endpoint vrátí stejný produkt pro více divizí, názvy budou například `Verva Diesel (varianta 1)` a `Verva Diesel (varianta 2)`; konkrétní divizi lze poznat podle atributu `division_id`.

## Sleva a výsledná cena

V nastavení integrace lze zadat buď pevnou slevu v částce, nebo procentní slevu. Obě pole nelze použít současně. Pokud zůstávají prázdná, stav senzoru představuje základní vyhlašovanou cenu.

Při nastavené slevě je stav senzoru cena po odečtení slevy. Zdrojová cena z portálu zůstává v atributu `announced_price`. Cenový senzor dále obsahuje:

- `price_type`: `base` nebo `discounted`,
- `discount_type`: `none`, `amount` nebo `percentage`,
- `discount_amount`: skutečně odečtená částka v měně senzoru,
- `discount_percentage`: nastavené procento, pouze při procentní slevě.

Výpočet se zaokrouhluje na dvě desetinná místa a výsledná cena neklesne pod nulu. Nastavení je dostupné přes **Nastavení → Zařízení a služby → Tankarta → Konfigurovat**.

## Ikony

Od verze 0.1.1 obsahuje integrace vlastní lokální brand obrázky pro světlý i tmavý režim. Cenové entity používají:

- běžná paliva: `mdi:gas-station`,
- AdBlue: `mdi:water-outline`,
- H2: `mdi:molecule`.

## Jednotka ceny

Endpoint vrací pouze `productPrice`, nikoli měnu ani jmenovatel ceny. Integrace proto používá konfigurovatelný kód měny, výchozí `CZK`. Netvrdí, zda je cena za litr, kilogram nebo jinou jednotku.

## Požadavky

- Home Assistant 2026.6 nebo novější,
- Browserless Chromium dostupný z Home Assistantu,
- účet na `business.tankarta.cz` bez povinného jednorázového 2FA při každém přihlášení.

Výchozí URL Browserless:

```text
http://db21ed7f-browserless-chrome:3000
```

Lze vložit také úplnou WebSocket URL z Changedetection. Integrace ji převede na HTTP endpoint `/chromium/function` a zachová parametry dotazu.

## Instalace přes HACS

1. V `custom_components/tankarta/manifest.json` nahraď `REPLACE_ME` svým GitHub účtem nebo organizací.
2. Nahraj celý repozitář na veřejný GitHub.
3. V HACS přidej repozitář jako vlastní repozitář typu **Integration**.
4. Stáhni integraci.
5. Restartuj Home Assistant.
6. Proveď tvrdý refresh prohlížeče.
7. Přidej **Tankarta** přes **Nastavení → Zařízení a služby → Přidat integraci**.

## Instalace ručně

Zkopíruj:

```text
custom_components/tankarta
```

do:

```text
/config/custom_components/tankarta
```

Restartuj Home Assistant a přidej integraci přes uživatelské rozhraní.

## Nastavení aktualizace a slevy

Výchozí interval je 360 minut. Interval i volitelnou slevu lze změnit v:

```text
Nastavení → Zařízení a služby → Tankarta → Konfigurovat
```

Povolený rozsah je 15 až 1440 minut.

## Diagnostika

Dočasně zapni debug logování:

```yaml
logger:
  logs:
    custom_components.tankarta: debug
```

Po restartu hledej zejména:

```text
Loaded 7 Tankarta price sensors; skipped 0 malformed items
```

Pokud config flow skončí chybou, podrobnost bude v **Nastavení → Systém → Protokoly** pod `custom_components.tankarta`.

## Bezpečnost

Heslo je uloženo v config entry Home Assistantu stejně jako u jiných UI integrací. Cookies a webové úložiště prohlížeče jsou uchovávány pouze v runtime paměti integrace a po restartu se zahodí.

Integrace úmyslně neloguje:

- uživatelské jméno ani heslo,
- Browserless token,
- cookies, local storage ani session storage,
- hodnotu `divisionID`,
- obsah neočekávaných HTTP odpovědí.

## Omezení

Portál není veřejné API a může změnit přihlašovací formulář nebo endpoint. Config flow při přidání integrace provede skutečné přihlášení a načtení cen, takže nefunkční selektory nebo změněný JSON zjistí před uložením konfigurace.


## Jak se ceny načítají

Endpoint `/Dashboard-ListPrice` není navigovatelná stránka. Dashboard jej volá jako AJAX `POST` s formulářovým tělem, `X-Requested-With`, aktivními cookies a dynamickým kontextem dashboardu. Integrace proto tělo požadavku nekonstruuje ani neukládá. Nechá dashboard požadavek vytvořit a zachytí pouze JSON odpověď.

Debug diagnostika může uvést metodu, Content-Type a délku těla požadavku, nikdy však jeho obsah, cookies ani tokeny.
