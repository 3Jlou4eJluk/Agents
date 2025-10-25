# Обновление классификатора - меньше отклонений

## ❌ Проблема

DeepSeek классификатор был слишком строгим:
- Отклонял потенциально релевантных лидов
- Требовал точного соответствия по всем критериям
- Фокусировался на поиске причин отклонить

**Результат:** Слишком много лидов не доходили до Stage 2 (letter generation).

## ✅ Решение

Изменен подход классификации:

### Было (строгая фильтрация):

```
"You are an expert ICP researcher analyzing if this person matches our target profile"

Consider:
1. Role & Seniority: Does their position match decision-making criteria?
2. Company Context: Company size, industry, growth stage
3. Pain Points: Do they likely face the problems we solve?
4. Decision Authority: Can they influence purchasing decisions?
```

Требовал соответствия по ВСЕМ критериям → много отклонений.

### Стало (мягкая пре-фильтрация):

```
"You are an ICP pre-screener. Your job is BROAD filtering - only reject OBVIOUS mismatches."

IMPORTANT: Default to "relevant" unless there are CLEAR red flags.

This is a PRE-SCREENING stage. Stage 2 will do deep research and make the final decision.
```

### Новая логика:

**Mark as relevant (✓) если:**
- Job title в релевантных функциях (tech, product, CS, ops, support)
- B2B tech/SaaS компания
- Manager+ уровень (есть влияние)
- **Сомневаешься → relevant** (better safe than sorry)

**Mark as NOT relevant (✗) ТОЛЬКО если:**
- Полностью нерелевантная функция (HR, finance, legal, sales, marketing)
- Явно не B2B tech/SaaS (retail, manufacturing)
- Явно junior IC без влияния (intern, junior dev)
- **OBVIOUS mismatch**

**When in doubt → mark as RELEVANT.** Stage 2 разберется.

## 📊 Ожидаемый результат

### До изменений:
- Stage 1 relevant: ~20-30%
- Stage 1 rejected: ~70-80% ⚠️ Слишком много!

### После изменений:
- Stage 1 relevant: ~60-80% ✅ Больше проходят
- Stage 1 rejected: ~20-40%
- Stage 2 (финальное решение): ~30-50% отклонений после глубокого исследования

## 🎯 Философия двух стадий

**Stage 1 (DeepSeek - быстро, дешево):**
- **Роль:** PRE-SCREENING
- **Задача:** Отсеять ОЧЕВИДНЫЙ мусор
- **Default:** INCLUDE (пропустить дальше)
- **Критерий:** Есть ли CLEAR red flags?

**Stage 2 (OpenAI - качество, глубина):**
- **Роль:** DEEP ANALYSIS
- **Задача:** Финальное решение после research
- **Default:** Investigate (исследовать LinkedIn, компанию)
- **Критерий:** После исследования - релевантен ли и стоит ли писать?

## ✅ Преимущества

1. **Меньше false negatives** - не отклоняем потенциально интересных лидов
2. **Экономия качества** - OpenAI делает финальное решение с полным контекстом
3. **Скорость + качество** - DeepSeek быстро фильтрует мусор, OpenAI глубоко анализирует остальных
4. **Баланс** - Stage 1 пропускает больше → Stage 2 делает качественный отсев

## 🧪 Тестирование

Запусти тест:
```bash
./test_run.sh
```

Проверь результаты:
```bash
python3 << 'EOF'
import pandas as pd
df = pd.read_csv('data/output/test_results.csv')

stage1_relevant = df['stage1_relevant'].sum()
stage1_total = len(df)
stage2_letters = df[df['stage2_rejected'] == False].shape[0]

print(f"Stage 1 relevant: {stage1_relevant}/{stage1_total} ({stage1_relevant/stage1_total*100:.1f}%)")
print(f"Stage 2 letters:  {stage2_letters}/{stage1_relevant} ({stage2_letters/stage1_relevant*100:.1f}% of relevant)")
