# Roadmap: Trading Bot

## Цель проекта
Создать проект, который можно показать на собеседовании для позиции **Python/BACKEND разработчик**.

---

## Структура проекта

```
trading-bot/  
src/  
core/  
data/  
strategy/  
backtest/  
execution/  
tests/  
README.md  
pyproject.toml
```


---

## Этап 0. Фундамент (Setup)
**Навыки**
- Python 3.11+, stdlib  
- typing, классы, исключения  
- Git

**Инструменты**
- venv/poetry
- IDE: VS Code/ PyCharm

**Результат**
- Репозиторий с базовой структурой

---

## Этап 1. Market Data Module
**Что**
- Загрузка OHLCV из API
- Кэширование по годам
- Загружаемые данные → pandas DataFrame

**Навыки**
- HTTP
- I/O файловые форматы
- обработка ошибок

**Проверка**
- Повторная загрузка из кеша
- Валидация данных

---

## Этап 2. Strategy Engine
**Что**
- Генерация сигналов BUY/SELL
- Изолированная логика
- Не работает с балансом

**Навыки**
- Чистые функции
- Абстракции

---

## Этап 3. Backtesting Engine
**Что**
- Виртуальный баланс
- Комиссии
- Журнал сделок (PnL, drawdown)

**Навыки**
- State management

---

## Этап 4. Reporting
**Что**
- Total PnL
- Win rate
- Equity curve

**Инструменты**
- pandas
- matplotlib/plotly

---

## Этап 5. Paper Trading Layer
**Что**
- Реальное время эмуляции
- API ошибки
- Задержки

---

## Этап 6. Архитектура
**Что**
- Чёткие границы модулей
- Dependency inversion
- Без глобального состояния

---

## Этап 7. Тестирование
**Что**
- Unit + интеграционные
- mocks

**Инструменты**
- pytest

---

## Этап 8. Документация
**Что**
- README
- Примеры запуска
- API описание
