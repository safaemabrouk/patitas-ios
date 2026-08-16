# Patitas — proyecto iOS

Generado con html2ios. Contiene una app nativa que muestra tu página web
empaquetada dentro del binario, así que **funciona sin conexión**.

| | |
|---|---|
| Nombre | Patitas |
| Identificador | `com.mypetpatitas.beta` |
| Versión | 1.0 (build 1) |
| iOS mínimo | 15.0 |
| Archivos web | 287 (50430 KB) |
| Origen | archivos empaquetados |

---

## Antes de nada

Necesitás **una cuenta del Apple Developer Program**: 99 dólares al año, en
<https://developer.apple.com/programs/>. La aprobación tarda entre unas horas y
dos días. No hay forma de publicar en la App Store sin ella.

No necesitás un Mac: todo lo demás se hace desde el navegador.

---

## Paso 1 · Crear la app en App Store Connect

1. Entrá en <https://appstoreconnect.apple.com> → **Mis apps** → **+** → **Nueva app**.
2. Plataforma: iOS. Nombre: el que verá la gente en la tienda.
3. **ID del paquete**: tiene que coincidir exactamente con `com.mypetpatitas.beta`.
   Si no aparece en la lista, crealo primero en
   <https://developer.apple.com/account/resources/identifiers/list>.
4. SKU: cualquier código interno, por ejemplo `patitas-001`.

## Paso 2 · Crear la clave de API

Esta clave es lo que permite compilar sin Mac: `xcodebuild` la usa para crear
por su cuenta los certificados y perfiles que hacen falta.

1. App Store Connect → **Usuarios y acceso** → **Integraciones** → **Claves** →
   **App Store Connect API** → **+**.
2. Rol: **App Manager** (necesita ese nivel para poder crear certificados).
3. Descargá el archivo `.p8`. **Sólo se puede descargar una vez.**
4. Anotá el **Key ID** y el **Issuer ID** que aparecen en esa pantalla.
5. Anotá también tu **Team ID**, en
   <https://developer.apple.com/account> → Membresía.

## Paso 3 · Subir el proyecto a GitHub

```bash
cd "Patitas"          # la carpeta que generó html2ios
git init
git add .
git commit -m "Primera versión"
git branch -M main
git remote add origin https://github.com/TU-USUARIO/TU-REPO.git
git push -u origin main
```

> Si el repositorio es **público**, los minutos de compilación en macOS son
> gratuitos. Si es privado, consumen cuota y cuestan diez veces más que los de
> Linux; para un proyecto pequeño igualmente entra en el plan gratuito, pero
> conviene saberlo.

## Paso 4 · Guardar los secretos

En tu repositorio: **Settings** → **Secrets and variables** → **Actions** →
**New repository secret**. Creá estos cuatro:

| Nombre | Contenido |
|---|---|
| `APPSTORE_KEY_ID` | El Key ID (10 caracteres, tipo `A1B2C3D4E5`) |
| `APPSTORE_ISSUER_ID` | El Issuer ID (un UUID largo) |
| `APPSTORE_PRIVATE_KEY` | El contenido **completo** del archivo `.p8`, incluidas las líneas `-----BEGIN PRIVATE KEY-----` y `-----END PRIVATE KEY-----` |
| `APPLE_TEAM_ID` | Tu Team ID (10 caracteres) |

Para copiar el `.p8` entero, abrilo con un editor de texto plano.
**No lo subas nunca al repositorio**: el `.gitignore` ya lo bloquea.

## Paso 5 · Compilar

En GitHub: pestaña **Actions** → *Compilar y subir a App Store Connect* →
**Run workflow**.

Tarda entre diez y veinte minutos. Cuando termina, la compilación aparece en
App Store Connect → tu app → **TestFlight**. Ahí podés instalarla en tu iPhone
antes de publicarla.

Cada ejecución sube automáticamente el número de build, porque Apple rechaza
dos envíos con el mismo número.

## Paso 6 · Enviar a revisión

En App Store Connect, en la ficha de tu app, hace falta:

- **Capturas de pantalla**: obligatorias para iPhone de 6,9 pulgadas
  (1320×2868). Podés sacarlas desde TestFlight en tu iPhone.
- **Descripción, palabras clave y categoría**.
- **URL de política de privacidad**: obligatoria siempre, aunque tu app no
  recoja ningún dato. Puede ser una página sencilla en GitHub Pages.
- **Privacidad de la app**: si no recogés datos, respondé que no recogés datos.
- **Clasificación por edades**.

Luego, **Añadir para revisión**. La revisión suele tardar entre uno y tres días.

---

## El riesgo real de esta app: la norma 4.2

Apple rechaza las apps que son sólo una web envuelta. La norma 4.2 del
reglamento de revisión dice que una app debe ofrecer algo más que una página
web reempaquetada. Es, de lejos, el motivo de rechazo más habitual para
proyectos como este.

Lo que ya juega a tu favor en este proyecto:

- **Funciona sin conexión.** Los archivos van dentro del binario, no se
  descargan. Esto es lo que más distingue una app de un marcador del navegador.
- **No se ve nada de navegador**: ni barra de direcciones, ni botones.
- **Tiene funciones nativas** disponibles desde tu JavaScript.

Lo que conviene que añadas antes de enviarla:

```javascript
// Estas funciones sólo existen dentro de la app; en el navegador no.
if (window.Native) {
  Native.haptic('light');                       // vibración al pulsar
  Native.share({ text: 'Mirá esto', url: '…' }); // menú nativo de compartir
  Native.open('https://ejemplo.com');           // abrir un enlace fuera
}
```

Usalas de verdad en tu página: vibración al acertar, compartir resultados, etc.
Y en la nota para el revisor explicá qué hace la app y por qué tiene sentido
como app y no como web. Si tu página además existe pública e idéntica en
internet, es probable que te la rechacen; conviene que la app aporte algo que
la web no tenga.

---

## Probar en tu iPhone antes de publicar

No hace falta esperar a la revisión. Una vez subida la compilación, entra en
TestFlight y la instalás en tu propio iPhone en dos minutos.

## Errores frecuentes

| Error | Qué pasa |
|---|---|
| `ITMS-90725: SDK version issue` | Se compiló con un Xcode viejo. El flujo ya comprueba que sea 26 o superior. |
| `No suitable application records were found` | El identificador del paquete no coincide con el de App Store Connect, o la app todavía no está creada allí. |
| `The bundle version must be higher` | Ese número de build ya se subió. Volvé a lanzar el flujo: sube solo. |
| `Authentication credentials are missing` | Alguno de los cuatro secretos está mal copiado, o al `.p8` le faltan las líneas BEGIN/END. |
| `No profiles for 'com.mypetpatitas.beta' were found` | La clave de API no tiene rol App Manager, o el Team ID es incorrecto. |

## Volver a generar

Si cambiás el HTML, volvé a ejecutar html2ios con `--force` y subí los cambios.
Sólo se sobrescribe la carpeta generada, no tu repositorio.
