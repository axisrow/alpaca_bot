# Формат данных кэша yfinance

Документация структуры данных, которые возвращает `DataLoader.load_market_data()`.

## Реальная структура yfinance (с group_by='ticker')

### MultiIndex структура

**Важно:** Структура MultiIndex отличается от того, как её использует код!

```
Columns: MultiIndex с 2 уровнями
├─ Level 0 (names='Ticker'): ['AAPL', 'GOOGL', 'MSFT', ...]  <- Тикеры
└─ Level 1 (names='Price'): ['Open', 'High', 'Low', 'Close', 'Volume']  <- OHLCV
```

**Формат:**
```
Ticker     AAPL              GOOGL             MSFT            ...
Price      Open High Low Close Volume  Open High Low Close Volume ...
Date
2024-11-07 176.63 180.28 ... 42137700  180.28 ...
2024-11-08 179.86 180.11 ... 38328800  ...
```

### Index (строки)

- **Type:** `pandas.DatetimeIndex`
- **Name:** 'Date'
- **Format:** ISO timestamp (timezone-naive)
- **Period:** 249 торговых дней (1 год)
- **Пример:** `['2024-11-07 00:00:00', '2024-11-08 00:00:00', '2024-11-11 00:00:00', ...]`

### Данные

- **Shape:** (249 дней, 3 тикера × 5 полей) = (249, 15)
- **Типы данных:**
  - `Open, High, Low, Close`: `float64`
  - `Volume`: `int64`
- **Null values:** Нет (0 NaN)
- **Memory:** ~30-40 KB (для 3 тикеров, 249 дней)

### Пример записи

```
                 AAPL Close      GOOGL Close      MSFT Close
Date
2024-11-07      226.426193      176.631059      455.160004
2024-11-08      226.157166      179.856814      458.359985
2025-11-06      269.769989      285.329987      432.450012
```

---

## Проблема: Несоответствие с кодом стратегий

### ❌ **КРИТИЧЕСКИЙ БАГ**

Стратегии используют:
```python
close_prices = data['Close']  # ← Ищет 'Close' в Level 0 (Ticker)
```

Но в реальности:
- **Level 0:** Тикеры (AAPL, GOOGL, MSFT, ...)
- **Level 1:** OHLCV поля (Close находится здесь!)

### Результат

```python
KeyError: 'Close'  # Потому что Close не в Level 0!
```

### Правильный синтаксис

```python
# Вариант 1: Использовать xs() с level=1
close = data.xs('Close', level=1, axis=1)
# Результат: DataFrame с тикерами в колонках

# Вариант 2: Выбрать все Close туплы
close = data[data.columns[data.columns.get_level_values('Price') == 'Close']]
```

---

## Тестирование формата

### Проверка через test_cache_debug.py

```bash
python test_cache_debug.py
```

**Результаты:**
- ✅ Pickle save/load: данные сохраняются 1:1
- ❌ Momentum calculation: падает с KeyError на `data['Close']`

### Integration test падает

```bash
pytest tests/test_paper_low.py::TestPaperLowIntegration::test_momentum_calculation_logic
```

**Output:**
```
KeyError: 'Close'
...
tests/test_paper_low.py:121: in test_momentum_calculation_logic
    close_prices = data['Close']
E   KeyError: 'Close'
```

---

## Почему тесты мокируют другую структуру?

В `tests/conftest.py` создается DataFrame с другой структурой:

```python
# Мокированная структура (НЕПРАВИЛЬНАЯ)
columns = pd.MultiIndex.from_arrays(
    [
        ["Close", "Close", "Volume", "Volume"],  # ← Level 0: Fields
        ["AAA", "BBB", "AAA", "BBB"],             # ← Level 1: Tickers
    ],
    names=["Field", "Ticker"],
)
```

Эта структура позволяет использовать `data['Close']`, но отличается от реальной yfinance!

---

## Кэширование: структура сохраняемых данных

### Сохранение
```python
# data_loader.py._save_to_cache()
with open(cache_path, "wb") as f:
    pickle.dump(data, f)  # ← Сохраняется как есть, без изменений
```

### Загрузка
```python
# data_loader.py._load_from_cache()
with open(cache_path, "rb") as f:
    data = pickle.load(f)  # ← Загружается идентично
```

**Вывод:** Кэш сохраняет данные **1:1 из yfinance**, поэтому имеет **ту же структуру**.

---

## Параметры yfinance

```python
# data_loader.py строка 70-76
download_kwargs = {
    "period": period,           # "1y" для стратегий
    "auto_adjust": True,        # Цены уже скорректированы
    "group_by": "ticker",       # ← Определяет структуру MultiIndex!
}

data = yf.download(tickers, **download_kwargs)
```

**group_by='ticker'** создает структуру:
- **Level 0:** Ticker names
- **Level 1:** OHLCV fields

---

## Рекомендации

### Краткосрочное (быстрое исправление)

Изменить стратегии для работы с реальной структурой:

```python
# Вместо:
close_prices = data['Close']

# Использовать:
close_prices = data.xs('Close', level=1, axis=1)
# или
close_prices = data.xs('Close', level='Price', axis=1)
```

### Долгосрочное (архитектурное)

1. Стандартизировать формат в `DataLoader`:
   - Либо переставить MultiIndex уровни
   - Либо переименовать уровни для ясности

2. Обновить мокированные данные в тестах:
   - Использовать реальную структуру
   - Убрать рассогласование с `conftest.py`

3. Добавить валидацию:
   - Проверять структуру MultiIndex при загрузке
   - Логировать ошибки структуры, а не только KeyError

---

## Верификация (test_cache_debug.py output)

```
STEP 1: Loading data from yfinance
Shape: (249, 15)
Column names: ['Ticker', 'Price']
Level 0: ['GOOGL', 'MSFT', 'AAPL']
Level 1: ['Open', 'High', 'Low', 'Close', 'Volume']

STEP 2: Testing pickle save/load cycle
✓ Data values match exactly (assert_frame_equal passed)

STEP 3: Comparing original vs loaded data
✓ Shape match
✓ Index match
✓ Columns match
✓ Dtypes match
✓ Data values match exactly
✗ Momentum calculation failed: 'Close'  ← КАК БУДТО!

STEP 4: Testing with DataLoader methods
✓ DataLoader save/load cycle is identical
```

**Вывод:** Кэширование работает идеально (1:1 pickle), но структура данных несовместима с кодом стратегий!
