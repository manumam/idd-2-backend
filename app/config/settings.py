"""Módulo de configuración centralizada de la aplicación.

Carga variables de entorno locales mediante Pydantic Settings, aplicando
validación de tipos y valores por defecto para todos los motores NoSQL.
Cumple con los requisitos RF16, RNF6 y RNF7 (separación de secretos del código).
"""

from typing import List, Optional
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Configuración general del servicio y adaptadores NoSQL."""

    # --- Configuración HTTP ---
    api_host: str = Field(default="0.0.0.0", alias="API_HOST")
    api_port: int = Field(default=8000, alias="API_PORT")
    api_debug: bool = Field(default=False, alias="API_DEBUG")
    db_timeout_seconds: float = Field(default=5.0, alias="DB_TIMEOUT_SECONDS")

    # --- MongoDB ---
    mongo_uri: str = Field(default="mongodb://localhost:27017", alias="MONGO_URI")
    mongo_database: str = Field(default="fixture2030", alias="MONGO_DATABASE")

    # --- Neo4j ---
    neo4j_uri: str = Field(default="bolt://localhost:7687", alias="NEO4J_URI")
    neo4j_user: str = Field(default="neo4j", alias="NEO4J_USER")
    neo4j_password: str = Field(default="password123", alias="NEO4J_PASSWORD")

    # --- Cassandra ---
    cassandra_hosts_raw: str = Field(default="localhost", alias="CASSANDRA_HOSTS")
    cassandra_port: int = Field(default=9042, alias="CASSANDRA_PORT")
    cassandra_keyspace: str = Field(default="fixture2030_comentarios", alias="CASSANDRA_KEYSPACE")

    @property
    def cassandra_hosts(self) -> List[str]:
        """Devuelve la lista de hosts para el cluster de Cassandra."""
        return [h.strip() for h in self.cassandra_hosts_raw.split(",") if h.strip()]

    # --- Redis ---
    redis_host: str = Field(default="localhost", alias="REDIS_HOST")
    redis_port: int = Field(default=6380, alias="REDIS_PORT")
    redis_db: int = Field(default=15, alias="REDIS_DB")
    redis_password: Optional[str] = Field(default=None, alias="REDIS_PASSWORD")

    # --- InfluxDB 3 ---
    influx_url: str = Field(default="http://127.0.0.1:8181", alias="INFLUX_URL")
    influx_database: str = Field(default="fixture2030_series_demo", alias="INFLUX_DATABASE")
    influx_token: Optional[str] = Field(default=None, alias="INFLUX_TOKEN")

    # --- InterSystems IRIS ---
    iris_host: str = Field(default="127.0.0.1", alias="IRIS_HOST")
    iris_port: int = Field(default=1972, alias="IRIS_PORT")
    iris_namespace: str = Field(default="USER", alias="IRIS_NAMESPACE")
    iris_user: str = Field(default="_SYSTEM", alias="IRIS_USER")
    iris_password: str = Field(default="SYS", alias="IRIS_PASSWORD")

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )


# Instancia singleton para ser inyectada en adaptadores y servicios
settings = Settings()
