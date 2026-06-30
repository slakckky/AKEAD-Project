# Invoice Mapping

Status: Erzwungener Testimport vorbereitet. Noch nicht importiert.

## Sicherheitsgrenzen

- Nur Datenbank `datenbank`.
- Keine automatische Anlage von `vendors`, `clients`, `produits` oder `stocks`.
- Zieltabellen bei Import: nur `invoices` und `invoices_details`.
- Kein `DELETE`, kein `DROP`.
- Import erst nach exakter Eingabe `JA`.

## Erzwungene Testwerte

- `id_org = 1`
- `id_dept = 1`
- `id_stock = 1` fuer Detailpositionen
- `id_stck = 1` fuer Rechnungskopf
- `id_vendor = 0` wie in der manuellen Testrechnung
- `id_clt = 1` wie in der manuellen Testrechnung
- `no_doc = R-25-005207` aus PDF-Staging
- `sy_uk = 510310100000016577` aus `MAX(sy_uk)+1` nach Eindeutigkeitspruefung
- Falls `pdf_import_items.product_id` vorhanden ist, wird dieser Wert nur verwendet, wenn der Artikel nicht aus `PDF_IMPORT`/`P01` stammt.
- Unsichere `PDF_IMPORT`/`P01`-Produktzuordnungen werden fuer `invoices_details.id_prd` ignoriert.
- Falls kein sicherer Artikel gefunden wird, wird weiter `id_prd=0` verwendet und gewarnt.

## Produktmapping

| PDF Artikel | Ziel `id_prd` | Status |
| --- | --- | --- |
| 10002 | 792 | Produkt gefunden |
| 1079 | 2283 | Produkt gefunden |
| 1380 | 2284 | Produkt gefunden |
| 1423 | 2285 | Produkt gefunden |
| 1078 | 2286 | Produkt gefunden |
| 1231 | 2287 | Produkt gefunden |
| 1233 | 2288 | Produkt gefunden |
| 749 | 2289 | Produkt gefunden |
| 1500 | 2384 | Produkt gefunden |
| 3011 | 1370 | Produkt gefunden |
| 3012 | 1371 | Produkt gefunden |
| 1483 | 2385 | Produkt gefunden |
| 1484 | 2290 | Produkt gefunden |
| 1485 | 2386 | Produkt gefunden |
| 1491 | 2387 | Produkt gefunden |
| 1492 | 2388 | Produkt gefunden |
| 1548 | 2389 | Produkt gefunden |
| 1549 | 2390 | Produkt gefunden |
| 1552 | 2391 | Produkt gefunden |
| 3501 | 2392 | Produkt gefunden |
| 3904 | 2393 | Produkt gefunden |
| 3905 | 2394 | Produkt gefunden |
| 3907 | 2291 | Produkt gefunden |
| 2012 | 2395 | Produkt gefunden |
| 82 | 2396 | Produkt gefunden |
| 728 | 2292 | Produkt gefunden |
| 782 | 2293 | Produkt gefunden |
| 1084 | 2294 | Produkt gefunden |
| 420 | 2397 | Produkt gefunden |
| 172 | 2398 | Produkt gefunden |
| 1329.1 | 2399 | Produkt gefunden |
| 328 | 2295 | Produkt gefunden |
| 2266 | 2296 | Produkt gefunden |
| 2361 | 2297 | Produkt gefunden |
| 3876 | 2400 | Produkt gefunden |
| 413 | 2298 | Produkt gefunden |
| 2202 | 2401 | Produkt gefunden |
| 3667 | 2402 | Produkt gefunden |
| 3652 | 2299 | Produkt gefunden |
| 3348 | 2403 | Produkt gefunden |
| 194 | 2300 | Produkt gefunden |
| 1526 | 2301 | Produkt gefunden |
| 1525 | 2302 | Produkt gefunden |
| 1524 | 2303 | Produkt gefunden |
| 2967 | 2304 | Produkt gefunden |
| 2215 | 2305 | Produkt gefunden |
| 4007 | 2306 | Produkt gefunden |
| 225 | 2307 | Produkt gefunden |
| 2023 | 2308 | Produkt gefunden |
| 1710 | 2309 | Produkt gefunden |
| 2237 | 2310 | Produkt gefunden |
| 2638 | 91 | Produkt gefunden |
| 2641 | 2311 | Produkt gefunden |
| 2640 | 2312 | Produkt gefunden |
| 1543.1 | 2313 | Produkt gefunden |
| 1874 | 2314 | Produkt gefunden |
| 2232 | 2315 | Produkt gefunden |
| 774.1 | 2316 | Produkt gefunden |
| 1219 | 2317 | Produkt gefunden |
| 2700 | 2318 | Produkt gefunden |
| 2701 | 2319 | Produkt gefunden |
| 772 | 2320 | Produkt gefunden |
| 773 | 2321 | Produkt gefunden |
| 1350 | 2322 | Produkt gefunden |
| 1083 | 2404 | Produkt gefunden |
| 2354 | 2323 | Produkt gefunden |
| 1388 | 2324 | Produkt gefunden |
| 1389 | 2325 | Produkt gefunden |
| 15923 | 2326 | Produkt gefunden |
| 6007 | 2327 | Produkt gefunden |
|  | 1910 | Produkt gefunden |
| 1 | 2328 | Produkt gefunden |
| 799 | 2235 | Produkt gefunden |
| 1256 | 2329 | Produkt gefunden |
| 1539 | 1499 | Produkt gefunden |
| 2201 | 2330 | Produkt gefunden |
| 1439 | 1499 | Produkt gefunden |
| 1516 | 1501 | Produkt gefunden |
| 1518 | 1500 | Produkt gefunden |
| 1894 | 2331 | Produkt gefunden |
| 1975 | 1487 | Produkt gefunden |
| 1976 | 1449 | Produkt gefunden |
| 1977 | 1644 | Produkt gefunden |
| 1113 | 1499 | Produkt gefunden |
| 1114 | 2332 | Produkt gefunden |
| 1381 | 1500 | Produkt gefunden |
| 1657 | 1501 | Produkt gefunden |
| 1961 | 1487 | Produkt gefunden |
| 1962 | 1488 | Produkt gefunden |
| 1963 | 1644 | Produkt gefunden |
| 3353 | 1963 | Produkt gefunden |
| 4030 | 965 | Produkt gefunden |
| 2192 | 479 | Produkt gefunden |
| 1493 | 1533 | Produkt gefunden |
| 1494 | 1533 | Produkt gefunden |
| 1585 | 2333 | Produkt gefunden |
| 1614 | 2334 | Produkt gefunden |
| 1615.1 | 2335 | Produkt gefunden |
| 1617 | 2336 | Produkt gefunden |
| 1479 | 2337 | Produkt gefunden |
| 1481 | 2405 | Produkt gefunden |
| 1582 | 2338 | Produkt gefunden |
| 1583 | 2339 | Produkt gefunden |
| 1882 | 2340 | Produkt gefunden |
| 1720 | 2341 | Produkt gefunden |
| 1722 | 1535 | Produkt gefunden |
| 2634 | 2342 | Produkt gefunden |
| 3313 | 2343 | Produkt gefunden |
| 1317 | 0 | nicht gefunden, erzwungen `id_prd=0` |
| 1318 | 2344 | Produkt gefunden |
| 435 | 2406 | Produkt gefunden |
| 96 | 2407 | Produkt gefunden |
| 1508 | 2408 | Produkt gefunden |
| 1509 | 2409 | Produkt gefunden |
| 1510 | 2410 | Produkt gefunden |
| 1821 | 2411 | Produkt gefunden |
| 286 | 2345 | Produkt gefunden |
| 291 | 2346 | Produkt gefunden |
| 282 | 2347 | Produkt gefunden |
| 29 | 2412 | Produkt gefunden |
| 440 | 2348 | Produkt gefunden |
| 1665 | 2413 | Produkt gefunden |
| 1666 | 2349 | Produkt gefunden |
| 1668 | 2350 | Produkt gefunden |
| 1752 | 2351 | Produkt gefunden |
| 112 | 2414 | Produkt gefunden |
| 1691.1 | 2352 | Produkt gefunden |
| 1891.1 | 2353 | Produkt gefunden |
| 242.1 | 2354 | Produkt gefunden |
| 243.1 | 2355 | Produkt gefunden |
| 246.1 | 2356 | Produkt gefunden |
| 3061 | 2357 | Produkt gefunden |
| 3144 | 2358 | Produkt gefunden |
| 2360 | 2359 | Produkt gefunden |
| 1501 | 2360 | Produkt gefunden |
| 2209 | 2415 | Produkt gefunden |
| 321 | 2361 | Produkt gefunden |
| 322 | 2362 | Produkt gefunden |
| 1571 | 2416 | Produkt gefunden |
| 2345 | 2363 | Produkt gefunden |
| 2346 | 2364 | Produkt gefunden |
| 1910 | 2365 | Produkt gefunden |
| 1224 | 2366 | Produkt gefunden |
| 1650 | 2367 | Produkt gefunden |
| 2052 | 2417 | Produkt gefunden |
| 2062 | 2418 | Produkt gefunden |
| 1457 | 2368 | Produkt gefunden |
| 1461 | 2369 | Produkt gefunden |
| 2228.1 | 2370 | Produkt gefunden |
| 2273.1 | 1118 | Produkt gefunden |
| 4011 | 2371 | Produkt gefunden |
| 4015 | 2372 | Produkt gefunden |
| 4016 | 1373 | Produkt gefunden |
| 3686 | 2419 | Produkt gefunden |
| 1711 | 2373 | Produkt gefunden |
| 1330 | 2420 | Produkt gefunden |
| 1331 | 2421 | Produkt gefunden |
| 2264 | 2422 | Produkt gefunden |
| 3713 | 2423 | Produkt gefunden |
| 646 | 2424 | Produkt gefunden |
| 1652 | 2425 | Produkt gefunden |
| 1643 | 2374 | Produkt gefunden |
| 807 | 2375 | Produkt gefunden |
| 806.3 | 2426 | Produkt gefunden |
| 1837 | 2376 | Produkt gefunden |
| 1988 | 2427 | Produkt gefunden |
| 2418 | 2377 | Produkt gefunden |
| 3206 | 2378 | Produkt gefunden |
| 1729.1 | 2428 | Produkt gefunden |
| 1730.1 | 2429 | Produkt gefunden |
| 1792.1 | 2430 | Produkt gefunden |
| 1817.1 | 2431 | Produkt gefunden |
| 867 | 2379 | Produkt gefunden |
| 1467 | 2380 | Produkt gefunden |
| 2374 | 2381 | Produkt gefunden |
| 2687 | 2432 | Produkt gefunden |
| 1429 | 2433 | Produkt gefunden |
| 746 | 1088 | Produkt gefunden |
| 747 | 1089 | Produkt gefunden |
| 3976 | 2434 | Produkt gefunden |
| 673 | 2382 | Produkt gefunden |
| 8 | 2383 | Produkt gefunden |

## Bewertung

Dieser Import ist ein erzwungener Testimport. Fachlich sichere Zuordnung ist weiterhin nicht vollstaendig.
Nicht gefundene Produkte: 1 von 182.
