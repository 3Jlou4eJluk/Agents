# Rate Limiting

Rate limiting middleware предотвращает ошибки 429 (Too Many Requests) от API провайдеров.

## Как это работает

### Token Bucket Algorithm

Используется алгоритм "token bucket":
- Есть "ведро" с токенами (размер = burst)
- Токены пополняются с постоянной скоростью (requests_per_second)
- Каждый запрос "берет" один токен
- Если токенов нет → запрос ждет

### Архитектура

```
create_llm()
  → ChatOpenAI
  → RateLimitedLLM(llm, rate_limiter)
  → bind_tools()
  → RateLimitedLLM(bound_llm, same_rate_limiter)
```

**Важно:**
- Один rate limiter на провайдера (singleton)
- OpenAI и DeepSeek имеют отдельные лимиты
- Rate limiter применяется ко ВСЕМ запросам (stage1, stage2, compression)

## Конфигурация

### config.json

```json
{
  "rate_limiting": {
    "enabled": true,
    "openai": {
      "requests_per_second": 3,
      "burst": 5,
      "note": "Conservative limits for Tier 1 API keys"
    },
    "deepseek": {
      "requests_per_second": 5,
      "burst": 10
    }
  }
}
```

### Параметры

- **`enabled`**: Включить/выключить rate limiting глобально
- **`requests_per_second`**: Средняя скорость запросов в секунду
- **`burst`**: Максимум одновременных запросов (для кратковременных всплесков)

### Рекомендуемые значения

**OpenAI:**
- Tier 1: `3 req/s, burst=5` (консервативно)
- Tier 2: `10 req/s, burst=20`
- Tier 3+: `50 req/s, burst=100`

**DeepSeek:**
- Standard: `5 req/s, burst=10`
- High volume: `20 req/s, burst=40`

**Определение tier:** https://platform.openai.com/settings/organization/limits

## Логирование

### DEBUG level (logs/orchestrator_*.log)

```
Rate limit reached, waiting 0.33s
LLM wrapped with rate limiter for provider 'openai'
```

### INFO level (console)

```
✓ Rate limiter for 'openai': 3 req/sec, burst=5
✓ Loaded config:
  - Rate limiting: ✓ ENABLED (openai: 3 req/s (burst=5), deepseek: 5 req/s (burst=10))
```

## Тестирование

Запусти тестовый скрипт:

```bash
python test_rate_limiting.py
```

Ожидаемый результат:
- 10 запросов выполняются за ~3.3 секунды (при 3 req/s)
- Нет ошибок 429
- Все запросы успешны

## Отключение

Для отключения rate limiting:

```json
{
  "rate_limiting": {
    "enabled": false
  }
}
```

**⚠️ Не рекомендуется!** Может привести к 429 ошибкам при параллельной обработке.

## Troubleshooting

### Все равно получаю 429

1. Уменьши `requests_per_second`:
   ```json
   "requests_per_second": 1
   ```

2. Уменьши `num_workers` в config:
   ```json
   "worker_pool": {
     "num_workers": 3  // вместо 5
   }
   ```

3. Проверь limits на платформе: https://platform.openai.com/settings/organization/limits

### Слишком медленно

1. Увеличь `requests_per_second` (если твой tier позволяет)
2. Увеличь `burst` для кратковременных всплесков
3. Используй более высокий tier API key

### Rate limiting не работает

Проверь, что используется config-based initialization:

```python
# ✓ Правильно (с rate limiting)
llm = create_llm(config, model_config)

# ✗ Неправильно (без rate limiting)
llm = ChatOpenAI(model="gpt-4o-mini", api_key="...")
```

Если видишь warning в логах:
```
LLM created in legacy mode without rate limiting
```

→ Переключись на config-based initialization.

## Технические детали

### Thread Safety

`TokenBucketRateLimiter` использует `asyncio.Lock` для безопасной работы с несколькими workers.

### Прозрачность

`RateLimitedLLM` полностью прозрачен:
- Проксирует все атрибуты к underlying LLM
- Перехватывает только `ainvoke()` и `bind_tools()`
- Совместим с LangChain tooling

### Накладные расходы

- Минимальные: ~0.1-0.5ms на запрос
- Ожидание включается только при превышении лимита
- Логирование только для ожиданий >0.1s
