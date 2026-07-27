# Changelog

## 0.1.3

- Opraveno načítání cen: `/Dashboard-ListPrice` je AJAX POST, nikoli GET.
- Integrace zachytává nativní POST vytvořený JavaScriptem dashboardu, takže zachová dynamické formulářové tělo, Origin, Referer, antiforgery údaje a cookies.
- Přidána samostatná diagnostika, zda byl cenový POST pozorován, včetně bezpečné délky a Content-Type těla bez jeho obsahu.
- Opraveno rozlišení login POST od cenového POST.

## 0.1.1

- přidány lokální brand ikony a loga pro světlý i tmavý režim,
- `divisionID` je dostupné jako atribut `division_id` cenového senzoru,
- interní unique ID zůstává neprůhledný hash a surové `divisionID` se neloguje,
- doplněna explicitní instalace po HACS: restart, tvrdý refresh a ruční přidání config entry,
- přidán bezpečný debug záznam s počtem vytvořených cenových senzorů.

## 0.1.0

- první verze.
