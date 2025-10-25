# Исправление ошибки Context Compression

## ❌ Проблема

После сжатия контекста (auto-compact) возникала ошибка:

```
Error code: 400 - {'error': {'message': "Invalid parameter: messages with role 'tool' must be a response to a preceeding message with 'tool_calls'.", 'type': 'invalid_request_error', 'param': 'messages.[2].role', 'code': None}}
```

### Причина:

OpenAI требует строгую последовательность:
```
AIMessage (с tool_calls) → ToolMessage (результат)
```

При compression сохранялись последние N сообщений, но могла быть разорвана пара:
```
AIMessage (tool_calls) [удалено при compression]
ToolMessage [сохранено]  ← ORPHANED! Нет предшествующего AIMessage
```

## ✅ Решение

### 1. Умное включение AIMessage (строки 226-238)

Если первое сообщение в `last_msgs` это `ToolMessage`, автоматически включаем предшествующий `AIMessage` с `tool_calls`:

```python
if last_msgs and isinstance(last_msgs[0], ToolMessage):
    # Find the preceding AIMessage with tool_calls
    for i in range(len(messages) + split_point - 1, 0, -1):
        if isinstance(messages[i], AIMessage) and messages[i].tool_calls:
            # Include it by expanding the window
            split_point = -(len(messages) - i)
            last_msgs = messages[split_point:]
            break
```

### 2. Валидация после compression (строки 309-331)

Дополнительная защита - удаляем orphaned ToolMessages:

```python
validated = []
last_had_tool_calls = False

for msg in compressed:
    if isinstance(msg, ToolMessage):
        if not last_had_tool_calls:
            # Orphaned - skip it
            logger.warning("Skipping orphaned ToolMessage")
            continue
        validated.append(msg)
        last_had_tool_calls = False
    elif isinstance(msg, AIMessage):
        validated.append(msg)
        last_had_tool_calls = msg.tool_calls and len(msg.tool_calls) > 0
    else:
        validated.append(msg)
        last_had_tool_calls = False
```

## 🔍 Как это работает

### До исправления:

```
messages = [
  HumanMessage,
  AIMessage (tool_calls),  ← В middle_msgs (сжимается)
  ToolMessage,             ← В last_msgs (сохраняется) ❌ ORPHANED
  AIMessage,
  ...
]

После compression:
[HumanMessage, SummaryMessage, ToolMessage, AIMessage, ...]
                                ↑ Нет предшествующего AIMessage!
```

### После исправления:

```
messages = [
  HumanMessage,
  AIMessage (tool_calls),  ← Автоматически включается!
  ToolMessage,             ← Теперь valid
  AIMessage,
  ...
]

После compression:
[HumanMessage, SummaryMessage, AIMessage (tool_calls), ToolMessage, AIMessage, ...]
                                ↑ Корректная пара!
```

## 📊 Логирование

В логах теперь видно:

```
DEBUG - Adjusted compression to include AIMessage at position 12 (has tool_calls)
INFO - 🗜️  Context compressed: 15 → 7 messages
```

Или, если всё равно нашелся orphaned:

```
WARNING - Skipping orphaned ToolMessage in compressed context
INFO - 🗜️  Context compressed: 15 → 6 messages
```

## ✅ Результат

- ✅ Нет ошибок 400 от OpenAI
- ✅ Compression работает корректно
- ✅ Tool calling не ломается
- ✅ Context window экономится

## 🧪 Тестирование

Проблема возникала при:
- Длинных цепочках MCP вызовов (>15 messages)
- Auto-compact triggered (trigger_at_messages=15)
- OpenAI модели (строгая валидация)

Теперь исправлено и протестировано.
