from aiogram.fsm.state import StatesGroup, State

class CartFlow(StatesGroup):
    # Пользователь выбирает способ доставки (первый раз)
    choosing_delivery = State()
    # Просмотр и подтверждение корзины
    reviewing = State()
    # Ожидание оплаты (заглушка)
    waiting_payment = State()
