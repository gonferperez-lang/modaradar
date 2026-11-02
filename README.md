# ModaRadar 📡👗

Vigila el **outlet y las rebajas de moda mujer** de tus tiendas favoritas y te **avisa en el móvil** en cuanto sacan prendas mucho más baratas.

- **Marcas destacadas: Zara, Brownie y Zadig&Voltaire.** Se revisan cada 15 minutos, tienen su propia pestaña y te avisan con prioridad desde un 30 % de descuento.
- **21 tiendas:** grandes de España y outlets (Fifty Outlet de Tendam, Desigual, Cortefiel, Bimba y Lola, Trucco, Misako, Superdry, Liu Jo), las marcas que pediste (Polo Club, Scuffers, Eme Studios, Yuxus, Nike) y Lola Casademunt, Compañía Fantástica, Laagam, Rouje y Pinko. Se añaden más en `config.toml`.
- **¿Outlet de Zara?** Zara no tiene outlet propio: su equivalente es la sección «Special prices», que ya se vigila, y en rebajas o Black Friday el radar añade solas esas secciones.
- **App para el móvil** (web instalable, se abre como una app normal): rebajas nuevas, 🔥 prendas a −50 %, segundas rebajas, buscador, tiendas y estado de los avisos.
- **Avisos push** al momento con la app gratuita **ntfy** (y, si quieres, por Telegram), con foto, precio, precio original, descuento y tallas.
- **Gratis**: funciona con GitHub Actions y GitHub Pages, con un [reloj propio](#revisión-puntual-cada-15-minutos-reloj) que lo lanza cada 15 minutos. No necesitas servidor ni ordenador encendido.

| Novedades | Destacadas | Buscar |
|---|---|---|
| Prendas que acaban de entrar en outlet, 🔥 −50 % y segundas rebajas | Zara, Brownie y Zadig por tipo de prenda, con el mayor descuento primero | Todo el outlet por prenda, tienda, talla y descuento |

---

## ¿Qué te avisa?

| Aviso | Cuándo |
|---|---|
| 🆕 **Nuevo en outlet** | Una prenda entra en rebajas/outlet con un **40 %** de descuento o más (**30 %** en Zara, Brownie y Zadig). |
| 🔥 **Chollo** | Cualquier prenda a **−50 %** o más: aviso prioritario. |
| 💸 **Rebajado aún más** | Una prenda ya rebajada baja **otro 10 %** (segundas rebajas, *last chance*…) o supera el umbral. |
| 🔁 **Vuelve a haber stock** | Una prenda rebajada que estaba agotada vuelve (o vuelve **tu talla**, si la configuras). |

Ejemplo de aviso:

```
⭐ Zara · −47 % · 🆕 Nuevo en outlet
Vestido mini abertura
15,99 € (antes 29,95 €)
Tallas: mira en la web
👗 Vestidos
```

Todo se ajusta en `config.toml` → `[notifications]`: los porcentajes, qué categorías te avisan (`ropa`, `calzado`, `bolsos`, `accesorios`), **tus tallas** (`mis_tallas = ["S", "M"]`) y palabras que siempre avisan con prioridad (`watchlist`, p. ej. «cachemir», «abrigo»).

> La primera pasada **memoriza** lo que ya está rebajado sin avisar. A partir de ahí, solo te llega lo nuevo.

## ¿Qué tiendas vigila y cómo?

Solo **webs oficiales** de cada marca, leyendo el catálogo público que ellas mismas publican (sin saltarse protecciones ni captchas, respetando su `robots.txt`).

| Tienda | Cómo se lee | Qué se vigila |
|---|---|---|
| ⭐ **Zara** | Catálogo JSON de su web | Su sección **«Special prices» de mujer** (todo el año) y, en cuanto las abre, las de **Rebajas / Black Friday / Sale**: el radar mira el menú cada 6 h y las añade sola. |
| ⭐ **Brownie** | Shopify (`browniespain.com`) | El catálogo completo de España: cualquier prenda con precio rebajado. |
| ⭐ **Zadig&Voltaire** | Su [API pública de catálogo](https://zadig-et-voltaire.com/llms.txt) | Toda la ropa de mujer + sus secciones de Rebajas, 2ª rebajas, Last chance y Outlet. |
| **Polo Club** | Shopify | Su colección de mujer y su outlet de mujer. Como casi todo está siempre rebajado, **avisa desde −60 %**. |
| **Scuffers** · **Eme Studios** · **Yuxus** | Shopify | Catálogo completo, solo lo que la marca etiqueta como de mujer (también venden ropa de hombre). |
| **Nike** | Sus páginas de ofertas de mujer | Las ~70 rebajas de mujer más nuevas en cada revisión (ropa y zapatillas). |
| **Fifty Outlet** | Su web (Salesforce) | El outlet oficial de Tendam: Women'secret, Springfield, Cortefiel y Pedro del Hierro. Hasta −88 %. |
| **Desigual** · **Cortefiel** · **Bimba y Lola** · **Liu Jo** 🇮🇹 · **Superdry** | Su web (Salesforce) | Sus secciones de outlet y rebajas de mujer (las primeras páginas, cada hora). |
| **Trucco** · **Misako** | Shopify | Catálogo completo (Misako es sobre todo bolsos y complementos). |
| Lola Casademunt · Compañía Fantástica · Laagam · Rouje 🇫🇷 · Pinko 🇮🇹 | Shopify | Catálogo completo. |

Las tiendas que no son destacadas se revisan cada 30 minutos para no saturarlas.

**Ten en cuenta**
- **Zara no publica las tallas** en su listado (su `robots.txt` no permite consultar la disponibilidad por talla). De Zara se avisa sin filtrar por talla y la app te dice «Tallas: en su web».
- **Zadig&Voltaire y Brownie** casi no tienen rebajas fuera de temporada (por ejemplo, a principios de noviembre de 2026 Zadig tenía 0 prendas rebajadas). Están vigiladas igual: el aviso llega en cuanto rebajen (Black Friday, rebajas de enero y verano).
- Solo se guardan prendas rebajadas al menos un **20 %** (`min_store_pct`); lo demás no se considera outlet.
- Se descartan solas la ropa de **hombre**, la **infantil** (también por las tallas: «4-5 años», «6», «8»…), perfumes, velas y tarjetas regalo.
- **Nike** no publica las tallas en su listado y de cada revisión solo se ven sus rebajas más nuevas; las anteriores siguen en la app unos días.

### Las marcas más buscadas en España

No hay un ranking oficial de «marcas más buscadas en Google». Como referencia se han usado las [webs de moda más visitadas en España según Semrush](https://nl.semrush.com/website/top/spain/fashion) (septiembre de 2026) y el [estudio de búsquedas en Google de JD Sports de 2025](https://www.marketingdirecto.com/anunciantes-general/publicaciones/marcas-moda-urbana-streetwear-espana-google-2025). Se han comprobado una a una (noviembre de 2026):

| | Marcas |
|---|---|
| ✅ **Vigiladas** | Zara · Nike · Polo Club · Scuffers · Eme Studios · Yuxus (además de Brownie, Zadig y el resto) |
| ⛔ **Bloquean el acceso automático** | El Corte Inglés y su outlet (también Sfera y Easy Wear) · Shein (captcha) · Mango y Mango Outlet · H&M, COS y & Other Stories · Pull&Bear, Bershka, Stradivarius, Massimo Dutti, Lefties y Oysho (protección anti-bots, aunque Zara sí deja) · Adidas · ASICS · Primark · Kiabi · Zalando · ASOS · Ralph Lauren · Levi's · Tommy Hilfiger · Calvin Klein · Guess · Lacoste · Decathlon · Uniqlo · Vans · The North Face · New Balance |
| ⛔ **Cargan los productos en el navegador** | On · Under Armour · Salomon |
| ⛔ **No venden en euros a España** | Juicy Couture (solo tienda de Reino Unido) |
| — | Vinted (segunda mano, no son rebajas de una marca) |

El radar **no se salta** captchas ni protecciones anti-bots. En la app (pestaña Tiendas) tienes el enlace directo a todas ellas.

---

## Puesta en marcha (unos 10 minutos)

> Lo más cómodo es hacerlo desde un ordenador. Solo hace falta una cuenta gratuita de GitHub.

### 1. Sube el proyecto a GitHub
1. Crea un repositorio **público** (por ejemplo `moderada`) en <https://github.com/new>. Tiene que ser público para que GitHub Pages y las Actions sean gratis.
2. Sube **todo** el contenido de esta carpeta, incluida la carpeta oculta `.github`. Puedes usar `git push` o el botón *Add file → Upload files*.

### 2. Elige tu canal privado de avisos
Inventa un nombre de tema difícil de adivinar, por ejemplo `modaradar-k8w2p7qx`. Funciona como una contraseña: quien lo conozca podrá leer tus avisos.

En GitHub: **Settings → Secrets and variables → Actions → New repository secret**
- Nombre: `NTFY_TOPIC` · Valor: tu tema (`modaradar-k8w2p7qx`)

### 3. Activa la web
**Settings → Pages → Build and deployment → Source: _GitHub Actions_**

### 4. Prepara el móvil
1. Instala **ntfy** (gratis) desde el App Store o Google Play.
2. En ntfy pulsa **+**, escribe tu tema y suscríbete. Acepta las notificaciones.

### 5. Primera ejecución
1. En GitHub, ve a **Actions → ModaRadar → Run workflow**, marca *Enviar solo un aviso de prueba* y pulsa *Run*. Te llegará «✅ ModaRadar conectado».
2. Vuelve a lanzar *Run workflow*, esta vez **sin** marcar la casilla. La primera pasada memoriza lo que ya está rebajado sin avisar. A partir de ahí se ejecuta sola y te avisa de cada rebaja nueva. Para que sea cada 15 minutos exactos, activa el [reloj](#revisión-puntual-cada-15-minutos-reloj).

### 6. Instala la app
Abre `https://TU-USUARIO.github.io/NOMBRE-DEL-REPO/` en **Safari** (iPhone) o **Chrome** (Android) → **Compartir** → **Añadir a pantalla de inicio**.

---

## La app

- **Novedades**: lo último que ha entrado en outlet, con filtros por categoría, tipo de prenda (vestidos, abrigos, punto…), tienda, orden (más nuevas, mayor descuento, más baratas), «solo con stock» y «mi talla». Pestañas **🔥 −50 %** y **💸 Bajadas** (segundas rebajas).
- **Destacadas**: Zara, Brownie y Zadig, agrupadas por tipo de prenda con el mayor descuento primero, y sus últimos avisos.
- **Buscar**: busca en todo el outlet («vestido negro», «piel», «cachemir»…). También busca por tipo: «abrigo» encuentra cazadoras y blazers.
- **Tiendas**: descuento medio y máximo de cada tienda, cuántas prendas tiene a −50 % y cuántas te avisaría.
- **Avisos**: estado del radar, tu talla, botón «Revisar» y el historial de todo lo que te ha avisado.
- **Ficha de cada prenda**: foto grande, precio y precio original, cuánto te ahorras, si es el **precio más bajo** que hemos visto, tallas con stock (tu talla resaltada) y prendas parecidas de otras tiendas.

**Tu talla en la app** (Avisos → Tu talla) se guarda solo en ese móvil y sirve para el filtro «Mi talla». Para que los **avisos** también filtren por talla, pon `mis_tallas` en `config.toml`.

## Botón «Revisar» (revisar las tiendas al momento)

El botón **📡 Revisar** de la app lanza el radar en GitHub sin esperar a la siguiente revisión programada. Tarda 1-2 minutos y después la app se actualiza sola. El botón ⟳ de al lado solo recarga los datos.

Se configura **una sola vez** en el móvil, desde la pestaña **Avisos → Botón «Revisar»**:
1. Crea un token en GitHub (*Settings → Developer settings → Fine-grained tokens → Generate new token*).
2. En *Repository access* elige **Only select repositories** → tu repositorio.
3. En *Permissions → Repository permissions → Actions* elige **Read and write**. No hace falta ningún otro permiso.
4. Pega el token en la app y pulsa **Guardar**.

El token se guarda solo en ese móvil (no se sube a ningún sitio) y solo sirve para lanzar el radar de este repositorio. Puedes borrarlo con **Quitar token** o revocarlo en GitHub cuando quieras.

## Revisión puntual cada 15 minutos (reloj)

El programador gratuito de GitHub (`schedule`) **no es puntual**: en la práctica se salta muchas ejecuciones y retrasa otras. Por eso el radar lleva su propio reloj, [`reloj.yml`](.github/workflows/reloj.yml), que no necesita servicios externos ni tokens:

1. Cada vuelta del reloj espera 15 minutos en el entorno **reloj** de GitHub. Ese temporizador (*Wait timer*) sí se cumple con puntualidad y no consume minutos.
2. Al terminar la espera, deja programada la siguiente vuelta y lanza la revisión de las tiendas (`monitor.yml`).
3. Si la cadena se rompiera (por ejemplo, por una caída de GitHub), la siguiente revisión que llegue por otra vía (el respaldo de GitHub, el botón «Revisar» o un cambio en la configuración) la vuelve a poner en marcha.

**Activación (una sola vez, 30 segundos):** en GitHub, ve a **Settings → Environments → reloj**, marca **Wait timer**, escribe **15** y pulsa **Save protection rules**. Después pulsa **Revisar** en la app para poner el reloj en marcha. Sin el temporizador, el reloj se detiene solo y avisa.

En la app, en **Avisos**, verás «⏱️ Reloj puntual activo» y la lista de *Últimas revisiones*.

## Conexión con las tiendas (24/7)

El radar se identifica siempre como `ModaRadar/1.0`, cumple el `robots.txt` de cada web y **no intenta saltarse protecciones**. Si una tienda le corta el paso (algunas lo hacen con los servidores de GitHub), hace una **pausa progresiva** (1 h, 2 h, 4 h… hasta 12 h) y vuelve a intentarlo sola. Las tiendas con catálogos grandes se consultan cada 30 minutos (`every_minutes`) para no saturarlas.

## Personalización (`config.toml`)

Puedes editarlo desde la propia web de GitHub, también en el móvil (o con el botón «Cambiar preferencias» de la app). Al guardar, el radar se ejecuta y se publica al momento.

- **`[notifications]`**: `min_discount_pct` (40), `destacadas_min_pct` (30), `chollo_pct` (50), `notify_price_drop_pct` (10), `notify_restock`, `categories`, `mis_tallas`, `watchlist`, `max_per_run`.
- **Marcar una tienda como destacada**: `destacada = true` (y `short` para el nombre corto de la pestaña).
- **Umbral propio de una tienda**: `min_discount_pct = 60` dentro de su `[[stores]]` (así está Polo Club).
- **Marcas que también venden ropa de hombre**: `women_terms = ["mujer", "woman"]` (solo cuenta lo que la marca etiqueta como de mujer).
- **Añadir una tienda Shopify**: abre `https://latienda.com/products.json`. Si ves texto con `"products"`, sirve:

```toml
[[stores]]
id = "mitienda"
name = "Mi Tienda"
platform = "shopify"
url = "https://www.mitienda.com"
locale = "/es-es"          # si tiene versión española (prueba https://www.mitienda.com/es-es/products.json)
max_pages = 8
every_minutes = 30
outlet_url = "https://www.mitienda.com/collections/outlet"
```

## Extras opcionales (secrets de GitHub)

| Secret | Para qué |
|---|---|
| `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` | Recibir también los avisos por Telegram, con foto (bot creado con @BotFather) |
| `NTFY_SERVER`, `NTFY_TOKEN` | Usar tu propio servidor ntfy o un tema protegido con contraseña |

## Ejecutarlo en tu ordenador

Necesitas Python 3.11 o superior. No hay que instalar dependencias.

```bash
python3 -m modaradar --dry-run        # revisa las tiendas sin enviar avisos
NTFY_TOPIC=tu-tema python3 -m modaradar --test-notify
python3 -m unittest discover -s tests # tests
cd docs && python3 -m http.server     # app en http://localhost:8000
```

## Cómo funciona

```
reloj.yml (cada 15 min) → GitHub Actions   (+ programador de GitHub como respaldo)
  └─ python -m modaradar
       ├─ sources/zara.py      secciones de rebajas de MUJER (Special prices, Rebajas, Black Friday…)
       ├─ sources/zadig.py     API pública de catálogo de Zadig&Voltaire
       ├─ sources/shopify.py   Brownie, Polo Club, Scuffers, Eme, Yuxus… (precio rebajado vs. original tachado)
       ├─ sources/nike.py      páginas de ofertas de mujer de Nike (lo más nuevo)
       ├─ sources/sfcc.py      outlets con Salesforce: Fifty Outlet, Desigual, Cortefiel, Bimba y Lola…
       ├─ filters.py   solo mujer · ropa / calzado / bolsos / accesorios · tipo de prenda · tallas
       ├─ state.py     detecta prendas nuevas en outlet, segundas rebajas y reposiciones
       ├─ analysis.py  descuento medio y máximo de cada tienda
       └─ notify.py    push al móvil (ntfy) / Telegram
  └─ guarda docs/data/*.json y publica docs/ en GitHub Pages → app del móvil
```
