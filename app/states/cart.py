from aiogram.fsm.state import StatesGroup, State

class CartFlow(StatesGroup):
    choosing_delivery = State()   # выбор способа доставки
    reviewing         = State()   # просмотр и подтверждение заказа
    waiting_payment   = State()   # ожидание оплаты (для будущей интеграции)
    entering_room     = State()   # ввод номера комнаты в профиле
