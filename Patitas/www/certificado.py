#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
certificado.py — crea el certificado de distribución de Apple sin un Mac.

Normalmente este certificado se genera con Acceso a Llaveros, que sólo existe
en macOS. Este script hace lo mismo desde Windows o Linux.

Se usa en dos tandas, con una visita a la web de Apple en medio:

    1)  py certificado.py solicitud
        Crea la clave privada y la solicitud (.csr) que sube a Apple.

    2)  [en developer.apple.com subís el .csr y descargás el .cer]

    3)  py certificado.py certificado distribution.cer
        Une el .cer con tu clave privada y deja el .p12 listo, además del
        texto que hay que pegar en el secreto de GitHub.

Necesita la biblioteca cryptography:
    py -m pip install cryptography
"""

import base64
import datetime
import sys
from pathlib import Path

CLAVE = Path("ios_distribution.key")
SOLICITUD = Path("ios_distribution.csr")
P12 = Path("distribution.p12")
CLAVE_B64 = Path("SECRETO_p12_base64.txt")

PASSWORD = "ragball"        # contraseña del .p12; va en otro secreto de GitHub


def falta_libreria():
    print("""
  ERROR: falta la biblioteca «cryptography».

  Instalala con este comando y volvé a intentarlo:

      py -m pip install cryptography
""")
    sys.exit(1)


try:
    from cryptography import x509
    from cryptography.x509.oid import NameOID
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.hazmat.primitives.serialization import pkcs12
except ImportError:
    falta_libreria()


def paso_solicitud(email, nombre, pais):
    if CLAVE.exists():
        print(f"\n  ATENCIÓN: {CLAVE} ya existe.")
        print("  Si la sobrescribís, el certificado que ya tengas dejará de servir.")
        if input("  ¿Sobrescribir? (escribí SI): ").strip() != "SI":
            print("  Cancelado.\n")
            return

    print("\n  Generando la clave privada (esto tarda unos segundos)...")
    clave = rsa.generate_private_key(public_exponent=65537, key_size=2048)

    CLAVE.write_bytes(clave.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption()))

    csr = (x509.CertificateSigningRequestBuilder()
           .subject_name(x509.Name([
               x509.NameAttribute(NameOID.EMAIL_ADDRESS, email),
               x509.NameAttribute(NameOID.COMMON_NAME, nombre),
               x509.NameAttribute(NameOID.COUNTRY_NAME, pais),
           ]))
           .sign(clave, hashes.SHA256()))

    SOLICITUD.write_bytes(csr.public_bytes(serialization.Encoding.PEM))

    print(f"""
  Listo. Se crearon dos archivos:

    {CLAVE}   ← tu clave privada. NO la borres ni la compartas.
    {SOLICITUD}   ← esto es lo que subís a Apple.

  Ahora, en la web de Apple:

    1. developer.apple.com/account/resources/certificates
    2. Botón +
    3. Elegí «Apple Distribution»
    4. Subí el archivo {SOLICITUD}
    5. Descargá el .cer que te da (se llamará algo como distribution.cer)
    6. Guardalo en esta misma carpeta

  Y después ejecutá:

      py certificado.py certificado distribution.cer
""")


def paso_certificado(ruta_cer):
    cer = Path(ruta_cer)
    if not cer.exists():
        print(f"\n  ERROR: no encuentro {cer}\n")
        sys.exit(1)
    if not CLAVE.exists():
        print(f"""
  ERROR: no encuentro {CLAVE}.

  Ese archivo se crea en el primer paso y es imprescindible: el certificado
  de Apple no sirve de nada sin la clave privada con la que se pidió.
  Si lo perdiste, hay que revocar el certificado en la web de Apple y
  empezar de nuevo con:  py certificado.py solicitud
""")
        sys.exit(1)

    datos = cer.read_bytes()
    try:
        cert = x509.load_der_x509_certificate(datos)
    except Exception:
        try:
            cert = x509.load_pem_x509_certificate(datos)
        except Exception:
            print("\n  ERROR: ese archivo no parece un certificado de Apple.\n")
            sys.exit(1)

    clave = serialization.load_pem_private_key(CLAVE.read_bytes(), password=None)

    # comprobar que la clave y el certificado se corresponden
    if (cert.public_key().public_numbers() != clave.public_key().public_numbers()):
        print(f"""
  ERROR: ese certificado no se corresponde con {CLAVE}.

  Suele pasar al descargar un certificado antiguo de la web de Apple.
  Descargá el que creaste con {SOLICITUD}, o generá una solicitud nueva.
""")
        sys.exit(1)

    nombre = cert.subject.rfc4514_string()
    caduca = cert.not_valid_after_utc if hasattr(cert, "not_valid_after_utc") else cert.not_valid_after

    # IMPORTANTE: cifrado antiguo (3DES + SHA1).
    #
    # Por defecto, esta biblioteca usa AES-256 con SHA-256, que es más seguro
    # pero que el llavero de macOS no sabe leer: al importarlo responde
    # «MAC verification failed», como si la contraseña fuese incorrecta.
    # Apple sólo acepta el formato PKCS#12 clásico.
    cifrado = (serialization.PrivateFormat.PKCS12.encryption_builder()
               .key_cert_algorithm(pkcs12.PBES.PBESv1SHA1And3KeyTripleDESCBC)
               .hmac_hash(hashes.SHA1())
               .build(PASSWORD.encode()))

    p12 = pkcs12.serialize_key_and_certificates(
        name=b"Apple Distribution",
        key=clave,
        cert=cert,
        cas=None,
        encryption_algorithm=cifrado)

    P12.write_bytes(p12)
    b64 = base64.b64encode(p12).decode()
    CLAVE_B64.write_text(b64, encoding="utf-8")

    print(f"""
  Certificado combinado correctamente, en el formato que acepta macOS.

    Titular ...... {nombre}
    Caduca ....... {caduca:%d/%m/%Y}

  Archivos creados:

    {P12}          ← el certificado completo
    {CLAVE_B64}   ← el texto para pegar en GitHub

  Ahora, en tu repositorio de GitHub, Settings → Secrets and variables →
  Actions, creá estos dos secretos:

    IOS_DIST_P12_BASE64      → todo el contenido de {CLAVE_B64}
    IOS_DIST_P12_PASSWORD    → {PASSWORD}

  El archivo del texto es largo: abrilo con el Bloc de notas, Ctrl+E para
  seleccionar todo, Ctrl+C para copiar.

  Y falta un tercero, el perfil de aprovisionamiento. En la web de Apple:

    1. developer.apple.com/account/resources/profiles
    2. Botón + → «App Store Connect» (en Distribution)
    3. Elegí tu App ID
    4. Elegí el certificado que acabás de crear
    5. Ponele de nombre exactamente:  RagBall AppStore
    6. Descargá el .mobileprovision y guardalo en esta carpeta
    7. Ejecutá:  py certificado.py perfil RagBall_AppStore.mobileprovision
""")


def paso_perfil(ruta):
    p = Path(ruta)
    if not p.exists():
        print(f"\n  ERROR: no encuentro {p}\n")
        sys.exit(1)
    b64 = base64.b64encode(p.read_bytes()).decode()
    salida = Path("SECRETO_perfil_base64.txt")
    salida.write_text(b64, encoding="utf-8")

    # el perfil es un contenedor firmado; el plist va dentro en texto plano
    crudo = p.read_bytes()
    ini, fin = crudo.find(b"<plist"), crudo.find(b"</plist>")
    nombre = "(no encontrado)"
    if ini != -1 and fin != -1:
        texto = crudo[ini:fin].decode("utf-8", "ignore")
        marca = "<key>Name</key>"
        if marca in texto:
            resto = texto.split(marca, 1)[1]
            nombre = resto.split("<string>", 1)[1].split("</string>", 1)[0]

    print(f"""
  Perfil leído correctamente.

    Nombre del perfil ... {nombre}

  Se creó {salida}. Creá en GitHub un tercer secreto:

    IOS_PROVISION_PROFILE_BASE64  → todo el contenido de {salida}

  Anotá el nombre del perfil, «{nombre}», porque tiene que coincidir
  exactamente con el que figura en el flujo de compilación.
""")


def paso_verificar():
    """Comprueba que el texto del secreto y la contraseña encajan."""
    if not CLAVE_B64.exists():
        print(f"\n  ERROR: no encuentro {CLAVE_B64}.\n"
              "  Ejecutá primero:  py certificado.py certificado distribution.cer\n")
        sys.exit(1)

    texto = CLAVE_B64.read_text(encoding="utf-8")
    limpio = "".join(texto.split())
    print(f"\n  El archivo tiene {len(texto)} caracteres "
          f"({len(limpio)} sin espacios ni saltos).")

    try:
        datos = base64.b64decode(limpio)
    except Exception:
        print("\n  ERROR: el texto no es base64 válido.\n")
        sys.exit(1)
    print(f"  Decodifica a {len(datos)} bytes.")

    try:
        clave, cert, _ = pkcs12.load_key_and_certificates(datos, PASSWORD.encode())
    except Exception:
        print(f"""
  ERROR: el certificado NO se abre con la contraseña «{PASSWORD}».

  Vuelve a generarlo:  py certificado.py certificado distribution.cer
""")
        sys.exit(1)

    print(f"""
  CORRECTO. El certificado y la contraseña encajan.

    Titular ........ {cert.subject.rfc4514_string()}
    Contraseña ..... {PASSWORD}

  Entonces el problema está en cómo se copió al secreto de GitHub.
  Volvé a crear IOS_DIST_P12_BASE64 pegando estos {len(limpio)} caracteres
  completos, sin que falte el principio ni el final.

  Los primeros 20:  {limpio[:20]}
  Los últimos 20:   {limpio[-20:]}

  En GitHub podés comprobar que pegaste todo mirando que empiece y termine
  igual que esas dos líneas.
""")


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return

    orden = sys.argv[1].lower()

    if orden in ("solicitud", "csr"):
        print("\n  Datos para la solicitud (se pueden dejar en blanco salvo el correo).\n")
        email = input("  Tu correo de Apple Developer: ").strip()
        if not email:
            print("\n  ERROR: el correo es obligatorio.\n"); sys.exit(1)
        nombre = input("  Tu nombre [Developer]: ").strip() or "Developer"
        pais = (input("  País, dos letras [MA]: ").strip() or "MA").upper()[:2]
        paso_solicitud(email, nombre, pais)

    elif orden in ("certificado", "cer", "p12"):
        if len(sys.argv) < 3:
            print("\n  Uso:  py certificado.py certificado distribution.cer\n"); sys.exit(1)
        paso_certificado(sys.argv[2])

    elif orden in ("verificar", "comprobar"):
        paso_verificar()

    elif orden == "perfil":
        if len(sys.argv) < 3:
            print("\n  Uso:  py certificado.py perfil archivo.mobileprovision\n"); sys.exit(1)
        paso_perfil(sys.argv[2])

    else:
        print(__doc__)


if __name__ == "__main__":
    main()
