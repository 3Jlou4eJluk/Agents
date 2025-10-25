# Тестирование Orchestrator

## 🧪 Быстрый тест (5 лидов)

### Файлы:
- **data/test_leads.csv** - 5 тестовых лидов (уже создан)
- **test_run.sh** - скрипт для быстрого запуска

### Тестовые лиды:
1. Sidney Pierce (Propel Software) - Customer Success Manager
2. Aman Khurana (Floqast) - Customer Success Manager  
3. Martin Ayala (Sonatafy Technology) - IT Manager
4. Chelsea Mclaughlin (Qgenda) - Sr. Customer Success Manager
5. Katie Klietz (Yello) - Senior Customer Success Manager

### Запуск теста:

**Вариант 1: Скрипт**
```bash
./test_run.sh
```

**Вариант 2: Напрямую**
```bash
python run.py \
  --input data/test_leads.csv \
  --output data/output/test_results.csv \
  --workers 5
```

### Ожидаемое время:
- **С текущими настройками:**
  - OpenAI: 0.25 req/s (очень консервативно)
  - DeepSeek: 5 req/s (быстро)
  - Stage 1 (DeepSeek): быстро (~30 сек для 5 лидов)
  - Stage 2 (OpenAI): медленно (~5-15 мин для 5 лидов)
  - **Итого: ~6-16 минут для 5 лидов**

### Мониторинг:

**Смотри в консоли:**
```
✓ Loaded config:
  - Classification: deepseek/deepseek-chat (temp=0)
  - Letter generation: openai/gpt-4o-mini (temp=0.8)
  - Rate limiting: ✓ ENABLED (openai: 0.25 req/s, deepseek: 5 req/s)

[Worker-W1] Processing: sidney.pierce@propelsoftware.com
[Worker-W1] ✓ Relevant (Stage 1): ...
[Worker-W1] 🔧 Generating letter (Stage 2)...
```

**Проверяй логи:**
```bash
tail -f logs/orchestrator_*.log
```

### Проверка результатов:

```bash
# Просмотр результатов
cat data/output/test_results.csv

# Или с pandas:
python3 << 'PYEOF'
import pandas as pd
df = pd.read_csv('data/output/test_results.csv')
print(df[['email', 'stage1_relevant', 'stage2_rejected', 'letter_subject']].to_string())
PYEOF
```

### Что проверять:

✅ **Успешная обработка:**
- Все 5 лидов обработаны
- Нет 429 ошибок от OpenAI
- Нет 429 ошибок от DeepSeek

✅ **Stage 1 (DeepSeek):**
- Работает быстро
- Корректно классифицирует (relevant=true/false)
- JSON parsing работает

✅ **Stage 2 (OpenAI):**
- Генерирует письма для relevant лидов
- Корректно отклоняет нерелевантных
- JSON parsing работает
- Письма персонализированы

✅ **Rate limiting:**
- В логах есть "Rate limit reached, waiting..." (нормально для OpenAI)
- Нет повторяющихся 429 ошибок

### Если есть проблемы:

**429 от OpenAI:**
```json
// Уменьши в config.json:
"openai": {
  "requests_per_second": 0.1,  // Ещё медленнее
  "burst": 1
}
```

**429 от DeepSeek:**
```json
// Уменьши в config.json:
"deepseek": {
  "requests_per_second": 2,  // Медленнее
  "burst": 5
}
```

**JSON parsing errors:**
- Проверь логи: `grep "JSON parsing" logs/*.log`
- Проверь промпты в worker_pool.py

### После успешного теста:

**Запуск полной обработки:**
```bash
python run.py \
  --input data/input/leads.csv \
  --output data/output/results.csv \
  --workers 5
```

**Ожидаемое время для 100 лидов:**
- ~2-3 часа (с консервативными лимитами)

**Прервать и продолжить позже:**
```bash
# Ctrl+C для остановки
# Продолжить с того же места:
python run.py \
  --input data/input/leads.csv \
  --output data/output/results.csv \
  --workers 5 \
  --resume
```
