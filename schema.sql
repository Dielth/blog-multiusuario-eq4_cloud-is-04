-- schema.sql  ·  Blog multiusuario IS-04 (Equipo 4)  ·  Base: blogdb en RDS MySQL 8.4
-- PROPUESTA de esquema basada en la interfaz actual. Mario puede ajustarla a su app.py.
-- Ejecutar desde la instancia EC2 (solo cuando el equipo lo acuerde):
--   mysql -h <endpoint-rds> -u admin -p blogdb < schema.sql
-- Las contraseñas NO se guardan en texto plano ni se escriben aquí: password_hash
-- debe generarse desde la app (por ejemplo, werkzeug.security.generate_password_hash).

USE blogdb;

SET NAMES utf8mb4;

CREATE TABLE IF NOT EXISTS usuarios (
  id            INT AUTO_INCREMENT PRIMARY KEY,
  nombre        VARCHAR(100) NOT NULL,
  usuario       VARCHAR(50)  NOT NULL UNIQUE,
  password_hash VARCHAR(255) NOT NULL,
  rol           ENUM('autor','moderador') NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS categorias (
  id     INT AUTO_INCREMENT PRIMARY KEY,
  nombre VARCHAR(60) NOT NULL UNIQUE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS entradas (
  id            INT AUTO_INCREMENT PRIMARY KEY,
  titulo        VARCHAR(200) NOT NULL,
  contenido     TEXT NOT NULL,
  autor_id      INT NOT NULL,
  categoria_id  INT NOT NULL,
  estado        ENUM('borrador','publicada','retirada') NOT NULL DEFAULT 'borrador',
  creado_en     TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  actualizado_en TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  CONSTRAINT fk_entradas_autor     FOREIGN KEY (autor_id)     REFERENCES usuarios(id),
  CONSTRAINT fk_entradas_categoria FOREIGN KEY (categoria_id) REFERENCES categorias(id),
  FULLTEXT KEY ft_busqueda (titulo, contenido)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- Un adjunto por fila. El archivo vive en S3; aquí solo se guarda su clave (ruta dentro del bucket).
CREATE TABLE IF NOT EXISTS adjuntos (
  id              INT AUTO_INCREMENT PRIMARY KEY,
  entrada_id      INT NOT NULL,
  nombre_original VARCHAR(255) NOT NULL,
  clave_s3        VARCHAR(500) NOT NULL,
  tipo_mime       VARCHAR(100),
  subido_en       TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT fk_adjuntos_entrada FOREIGN KEY (entrada_id) REFERENCES entradas(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ---------------------------------------------------------------------------
-- DATOS DE PRUEBA (3 usuarios, 2 categorías, 4 entradas con 1 borrador, 4 adjuntos)
-- Los password_hash son marcadores: reemplazarlos por hashes reales generados por la app.
-- El texto de las entradas es de ejemplo.
-- ---------------------------------------------------------------------------

INSERT INTO usuarios (id, nombre, usuario, password_hash, rol) VALUES
  (1, 'Ana García',    'ana',    'REEMPLAZAR_HASH', 'autor'),
  (2, 'Carlos Ruiz',   'carlos', 'REEMPLAZAR_HASH', 'autor'),
  (3, 'Laura Méndez',  'laura',  'REEMPLAZAR_HASH', 'moderador');

INSERT INTO categorias (id, nombre) VALUES
  (1, 'Infraestructura'),
  (2, 'Seguridad');

INSERT INTO entradas (id, titulo, contenido, autor_id, categoria_id, estado) VALUES
  (1, 'Arquitectura Cloud en AWS para PyMEs',
      'Contenido de ejemplo sobre arquitectura en la nube para pequeñas y medianas empresas.', 1, 1, 'publicada'),
  (2, 'Buenas prácticas de seguridad en la nube',
      'Contenido de ejemplo sobre buenas prácticas de seguridad e IAM.', 2, 2, 'publicada'),
  (3, 'Ventajas del almacenamiento de objetos con S3',
      'Contenido de ejemplo sobre las ventajas del almacenamiento de objetos.', 1, 1, 'publicada'),
  (4, 'Borrador: Migración a contenedores en producción',
      'Borrador de ejemplo, aún no visible para el público.', 2, 2, 'borrador');

INSERT INTO adjuntos (entrada_id, nombre_original, clave_s3, tipo_mime) VALUES
  (1, 'diagrama-arquitectura.png', 'uploads/diagrama-arquitectura.png', 'image/png'),
  (2, 'guia-seguridad-iam.pdf',    'uploads/guia-seguridad-iam.pdf',    'application/pdf'),
  (3, 'almacenamiento-nube.jpg',   'uploads/almacenamiento-nube.jpg',   'image/jpeg'),
  (4, 'borrador-esquema.png',      'uploads/borrador-esquema.png',      'image/png');

-- Verificación rápida (para la captura "después"):
--   SHOW TABLES;
--   SELECT id, titulo, estado FROM entradas;
