package config

import (
    "errors"
    "gopkg.in/yaml.v3"
    "os"
    "path/filepath"
)

// Поиск config.yml: 1. CONFIG_PATH 2. вверх по дереву
func findConfigFile(filename string) (string, error) {
    configPath := os.Getenv("CONFIG_PATH")
    if configPath != "" {
        if fi, err := os.Stat(configPath); err == nil && !fi.IsDir() {
            return configPath, nil
        }
        return "", errors.New("CONFIG_PATH is set but file not found: " + configPath)
    }
    dir, err := os.Getwd()
    if err != nil {
        return "", err
    }
    for {
        candidate := filepath.Join(dir, filename)
        if fi, err := os.Stat(candidate); err == nil && !fi.IsDir() {
            return candidate, nil
        }
        parent := filepath.Dir(dir)
        if parent == dir {
            break
        }
        dir = parent
    }
    return "", errors.New("Config file not found. Please specify CONFIG_PATH or place config.yml above the working directory")
}

// Загрузка YAML-конфига в структуру
func LoadConfig(cfg any) error {
    path, err := findConfigFile("config.yml")
    if err != nil {
        return err
    }
    data, err := os.ReadFile(path)
    if err != nil {
        return err
    }
    return yaml.Unmarshal(data, cfg)
}
