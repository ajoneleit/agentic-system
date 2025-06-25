"""Configuration utilities for the Agentic Coding System.

This module provides helper functions for configuration management,
environment variable handling, and settings validation.
"""

import os
from pathlib import Path
from typing import Any, Dict, Optional, Type, TypeVar, Union

import yaml
from pydantic import BaseModel, ValidationError
from structlog import get_logger

from config import Environment, Settings, get_settings
from src.core.exceptions import ConfigurationError, InvalidConfigurationError, MissingConfigurationError


logger = get_logger(__name__)
T = TypeVar("T", bound=BaseModel)


def load_yaml_config(config_path: Union[str, Path]) -> Dict[str, Any]:
    """Load configuration from a YAML file.
    
    Args:
        config_path: Path to YAML configuration file
        
    Returns:
        Configuration dictionary
        
    Raises:
        ConfigurationError: If file cannot be loaded
    """
    config_path = Path(config_path)
    
    if not config_path.exists():
        raise ConfigurationError(
            f"Configuration file not found: {config_path}",
            error_code="CONFIG_FILE_NOT_FOUND",
            details={"path": str(config_path)},
        )
    
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            config = yaml.safe_load(f)
            
        if not isinstance(config, dict):
            raise InvalidConfigurationError(
                "config",
                "Configuration file must contain a dictionary at root level",
                suggestion="Ensure your YAML file starts with key-value pairs",
            )
            
        logger.info("Loaded configuration from YAML", path=str(config_path))
        return config
        
    except yaml.YAMLError as e:
        raise InvalidConfigurationError(
            "config",
            f"Invalid YAML format: {e}",
            suggestion="Check YAML syntax using a validator",
        ) from e
    except Exception as e:
        raise ConfigurationError(
            f"Failed to load configuration: {e}",
            error_code="CONFIG_LOAD_ERROR",
            details={"path": str(config_path), "error": str(e)},
        ) from e


def merge_configs(*configs: Dict[str, Any]) -> Dict[str, Any]:
    """Deep merge multiple configuration dictionaries.
    
    Later configurations override earlier ones. Lists are replaced, not merged.
    
    Args:
        *configs: Configuration dictionaries to merge
        
    Returns:
        Merged configuration dictionary
    """
    result = {}
    
    for config in configs:
        if not config:
            continue
            
        for key, value in config.items():
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                # Recursively merge dictionaries
                result[key] = merge_configs(result[key], value)
            else:
                # Replace value (including lists)
                result[key] = value
    
    return result


def validate_config(config_dict: Dict[str, Any], model_class: Type[T]) -> T:
    """Validate configuration dictionary against a Pydantic model.
    
    Args:
        config_dict: Configuration dictionary
        model_class: Pydantic model class to validate against
        
    Returns:
        Validated model instance
        
    Raises:
        InvalidConfigurationError: If validation fails
    """
    try:
        return model_class(**config_dict)
    except ValidationError as e:
        errors = []
        for error in e.errors():
            field = ".".join(str(x) for x in error["loc"])
            msg = error["msg"]
            errors.append(f"{field}: {msg}")
            
        raise InvalidConfigurationError(
            "config",
            f"Configuration validation failed: {'; '.join(errors)}",
            suggestion="Check the required fields and types in your configuration",
        ) from e


def get_env_var(
    key: str,
    default: Optional[str] = None,
    required: bool = False,
    var_type: Type = str,
) -> Optional[Any]:
    """Get environment variable with type conversion.
    
    Args:
        key: Environment variable name
        default: Default value if not found
        required: Whether the variable is required
        var_type: Type to convert the value to
        
    Returns:
        Environment variable value or default
        
    Raises:
        MissingConfigurationError: If required and not found
        InvalidConfigurationError: If type conversion fails
    """
    value = os.environ.get(key, default)
    
    if value is None and required:
        raise MissingConfigurationError(key, env_var=key)
    
    if value is None:
        return None
    
    # Type conversion
    if var_type == bool:
        return value.lower() in ("true", "yes", "1", "on")
    
    try:
        return var_type(value)
    except (ValueError, TypeError) as e:
        raise InvalidConfigurationError(
            key,
            f"Cannot convert '{value}' to {var_type.__name__}: {e}",
            suggestion=f"Ensure {key} contains a valid {var_type.__name__} value",
        ) from e


def load_env_file(env_path: Union[str, Path] = ".env") -> Dict[str, str]:
    """Load environment variables from a file.
    
    Args:
        env_path: Path to environment file
        
    Returns:
        Dictionary of loaded environment variables
    """
    env_path = Path(env_path)
    loaded_vars = {}
    
    if not env_path.exists():
        logger.debug("Environment file not found", path=str(env_path))
        return loaded_vars
    
    try:
        with open(env_path, "r", encoding="utf-8") as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()
                
                # Skip empty lines and comments
                if not line or line.startswith("#"):
                    continue
                
                # Parse key=value
                if "=" not in line:
                    logger.warning(
                        "Invalid line in env file",
                        path=str(env_path),
                        line_num=line_num,
                        line=line,
                    )
                    continue
                
                key, value = line.split("=", 1)
                key = key.strip()
                value = value.strip()
                
                # Remove quotes if present
                if value and value[0] == value[-1] and value[0] in ('"', "'"):
                    value = value[1:-1]
                
                # Set in environment and track
                os.environ[key] = value
                loaded_vars[key] = value
        
        logger.info(
            "Loaded environment variables",
            path=str(env_path),
            count=len(loaded_vars),
        )
        
    except Exception as e:
        logger.error(
            "Failed to load environment file",
            path=str(env_path),
            error=str(e),
        )
    
    return loaded_vars


def get_config_path(
    config_name: str,
    environment: Optional[Environment] = None,
    config_dir: Union[str, Path] = "config",
) -> Path:
    """Get configuration file path for a specific environment.
    
    Looks for files in this order:
    1. config/{config_name}.{environment}.yaml
    2. config/{config_name}.yaml
    
    Args:
        config_name: Base name of configuration file
        environment: Environment to load config for
        config_dir: Directory containing config files
        
    Returns:
        Path to configuration file
        
    Raises:
        ConfigurationError: If no configuration file found
    """
    config_dir = Path(config_dir)
    
    if environment is None:
        settings = get_settings()
        environment = settings.environment
    
    # Try environment-specific config first
    env_config_path = config_dir / f"{config_name}.{environment.value}.yaml"
    if env_config_path.exists():
        return env_config_path
    
    # Fall back to default config
    default_config_path = config_dir / f"{config_name}.yaml"
    if default_config_path.exists():
        return default_config_path
    
    raise ConfigurationError(
        f"No configuration file found for '{config_name}'",
        error_code="CONFIG_NOT_FOUND",
        details={
            "searched_paths": [
                str(env_config_path),
                str(default_config_path),
            ],
            "environment": environment.value,
        },
    )


def validate_api_key(api_key: Optional[str], service: str = "Anthropic") -> str:
    """Validate and return API key.
    
    Args:
        api_key: API key to validate
        service: Service name for error messages
        
    Returns:
        Validated API key
        
    Raises:
        MissingConfigurationError: If API key is missing
        InvalidConfigurationError: If API key format is invalid
    """
    if not api_key:
        raise MissingConfigurationError(
            f"{service.lower()}_api_key",
            env_var=f"{service.upper()}_API_KEY",
        )
    
    # Basic format validation
    if len(api_key) < 10:
        raise InvalidConfigurationError(
            f"{service.lower()}_api_key",
            "API key appears to be too short",
            suggestion=f"Ensure you have copied the complete {service} API key",
        )
    
    if " " in api_key:
        raise InvalidConfigurationError(
            f"{service.lower()}_api_key",
            "API key contains spaces",
            suggestion="Remove any spaces from the API key",
        )
    
    return api_key


class ConfigManager:
    """Manages configuration loading and validation."""
    
    def __init__(
        self,
        config_dir: Union[str, Path] = "config",
        env_file: Union[str, Path] = ".env",
    ):
        """Initialize configuration manager.
        
        Args:
            config_dir: Directory containing configuration files
            env_file: Path to environment file
        """
        self.config_dir = Path(config_dir)
        self.env_file = Path(env_file)
        self._cache: Dict[str, Any] = {}
    
    def load_settings(
        self,
        environment: Optional[Environment] = None,
        overrides: Optional[Dict[str, Any]] = None,
    ) -> Settings:
        """Load and validate application settings.
        
        Args:
            environment: Override environment
            overrides: Configuration overrides
            
        Returns:
            Validated settings instance
        """
        # Load environment variables
        load_env_file(self.env_file)
        
        # Determine environment
        if environment is None:
            env_str = get_env_var("ACS_ENVIRONMENT", default="development")
            environment = Environment(env_str)
        
        # Build configuration from multiple sources
        config = {}
        
        # Try to load base configuration
        try:
            base_config_path = get_config_path("settings", environment, self.config_dir)
            config = load_yaml_config(base_config_path)
        except ConfigurationError:
            logger.info("No configuration file found, using environment variables only")
        
        # Apply overrides
        if overrides:
            config = merge_configs(config, overrides)
        
        # Add environment to config
        config["environment"] = environment.value
        
        # Validate and create settings
        try:
            settings = Settings(**config)
            logger.info(
                "Settings loaded successfully",
                environment=environment.value,
                debug=settings.debug,
            )
            return settings
        except ValidationError as e:
            # Re-raise as our custom exception
            validate_config(config, Settings)
            raise  # Should never reach here
    
    def get_config(
        self,
        config_name: str,
        model_class: Type[T],
        environment: Optional[Environment] = None,
        use_cache: bool = True,
    ) -> T:
        """Load and validate a configuration file.
        
        Args:
            config_name: Name of configuration file (without extension)
            model_class: Pydantic model class for validation
            environment: Override environment
            use_cache: Whether to use cached configuration
            
        Returns:
            Validated configuration instance
        """
        cache_key = f"{config_name}:{environment}"
        
        if use_cache and cache_key in self._cache:
            return self._cache[cache_key]
        
        # Load configuration
        config_path = get_config_path(config_name, environment, self.config_dir)
        config_dict = load_yaml_config(config_path)
        
        # Validate
        config = validate_config(config_dict, model_class)
        
        # Cache
        if use_cache:
            self._cache[cache_key] = config
        
        return config
    
    def clear_cache(self) -> None:
        """Clear configuration cache."""
        self._cache.clear()
        logger.debug("Configuration cache cleared")


# Global config manager instance
_config_manager: Optional[ConfigManager] = None


def get_config_manager() -> ConfigManager:
    """Get or create global config manager instance.
    
    Returns:
        ConfigManager instance
    """
    global _config_manager
    if _config_manager is None:
        _config_manager = ConfigManager()
    return _config_manager