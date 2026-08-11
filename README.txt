ALEX FORTUNA - VERSION WEB
============================

Esta versión está preparada para subir a un servidor y funcionar desde celulares.

Rutas:
 /             consulta pública
 /admin/login  acceso del administrador
 /admin        panel de ventas
 /salud        prueba del servicio

Variables de entorno:
 SECRET_KEY
 ADMIN_USER
 ADMIN_PASSWORD
 DATABASE_URL

Para producción se recomienda PostgreSQL (ya está contemplado en render.yaml).
No publiques el panel sin contraseña.

Para probar localmente:
  pip install -r requirements.txt
  python app.py

Para desplegar en Render:
1. Sube esta carpeta a un repositorio GitHub.
2. En Render crea un servicio usando el archivo render.yaml.
3. Define ADMIN_USER y ADMIN_PASSWORD.
4. Render creará la base PostgreSQL.
5. Obtendrás una dirección pública para compartir por WhatsApp.

IMPORTANTE:
La dirección pública dependerá del proveedor de hosting. El dominio propio
(por ejemplo alexfortuna.com) se configura después, cuando tengas dominio.
