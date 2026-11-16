# CloudBlog UAQ - Blog Multiusuario con Archivos en la Nube

Proyecto final de la materia **Servicios Cloud (IS-04)** - Facultad de Informatica, Universidad Autonoma de Queretaro (UAQ) - **Equipo 4**.

Aplicacion web multiusuario desarrollada en **Python (Flask)** y desplegada sobre infraestructura de **Amazon Web Services (AWS)**, disenada para publicar articulos tecnicos, gestionar archivos adjuntos de forma privada en la nube, moderar contenido y administrar usuarios por roles.

## Arquitectura en la Nube (AWS)

* **Computo (Amazon EC2):** Instancia Amazon Linux ejecutando la aplicacion Flask administrada como servicio continuo mediante systemd (cloudblog.service).
* **Base de Datos Relacional (Amazon RDS - MySQL):** Almacena usuarios, roles, categorias, publicaciones, metadatos de adjuntos y comentarios con integridad referencial.
* **Almacenamiento de Objetos (Amazon S3):** Bucket privado donde se resguardan los archivos adjuntos (imagenes, PDFs y documentos) servidos de forma controlada a traves del backend.
* **Seguridad y Permisos (AWS IAM):** Autenticacion mediante rol IAM asignado a la instancia EC2 para operar sobre S3 sin exponer llaves de acceso estaticas en el codigo fuente.

## Funcionalidades Implementadas

### 1. Gestion de Usuarios y Seguridad
* **Control de Acceso Basado en Roles (RBAC):**
  * **Autor:** Puede redactar, editar, publicar o guardar como borrador sus propias entradas, adjuntar archivos y comentar.
  * **Moderador:** Acceso global para publicar/retirar cualquier entrada del blog y administrar usuarios (promover a moderador, degradar a autor o eliminar cuentas).
* **Registro y Autenticacion Segura:**
  * Contrasenas almacenadas mediante hash criptografico (Werkzeug).
  * Validacion de complejidad minima de 8 caracteres (mayusculas, minusculas y numeros) con indicador visual en tiempo real.
  * Boton para alternar la visibilidad de la contrasena en inicio de sesion y registro.

### 2. Publicaciones y Almacenamiento en S3
* **Zona Drag & Drop:** Carga de archivos arrastrando y soltando con vista previa inmediata antes de guardar.
* **Previsualizacion en Portada:** Miniaturas de imagenes, vista incrustada de PDFs e indicadores por tipo de archivo en el listado principal.
* **Visor Modal Superpuesto:** Botones separados para Visualizar y Descargar. Permite inspeccionar imagenes, PDFs y documentos de texto sobre la misma pagina con opciones para compartir enlace, descargar, abrir en pestana nueva, pantalla completa e imprimir.
* **Eliminacion Sincronizada:** Al borrar una publicacion o un usuario, se eliminan automaticamente los objetos asociados en Amazon S3 y los registros dependientes en Amazon RDS.

### 3. Sistema de Comentarios y Busqueda
* **Comentarios Persistentes:** Los usuarios con sesion iniciada publican directamente; los visitantes sin sesion son redirigidos al inicio de sesion o registro y su comentario se conserva y publica automaticamente al autenticarse.
* **Busqueda y Filtrado:** Filtrado de publicaciones por palabra clave, categoria y autor.

## Estructura del Repositorio

* app.py: Servidor Flask, rutas, logica de negocio, conexion RDS y S3.
* schema.sql: Esquema relacional MySQL (usuarios, categorias, entradas, adjuntos, comentarios).
* requirements.txt: Dependencias Python con versiones fijadas.
* .env.example: Plantilla de variables de entorno requeridas.
* templates/: Plantillas HTML con Bootstrap 5 y Bootstrap Icons (base.html, index.html, post.html, editor.html, panel.html, usuarios.html, login.html, registro.html).

## Instalacion y Despliegue

1. Clonar el repositorio:
   git clone https://github.com/Dielth/blog-multiusuario-eq4_cloud-is-04.git
2. Instalar dependencias:
   pip3 install -r requirements.txt
3. Configurar variables de entorno:
   cp .env.example .env
4. Importar schema.sql en Amazon RDS (MySQL).
5. Ejecutar la aplicacion:
   sudo python3 app.py
