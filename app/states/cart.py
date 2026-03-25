from aiogram.fsm.state import StatesGroup, State


class CartFlow(StatesGroup):
    choosing_delivery = State()
    reviewing = State()
    waiting_payment = State()
    entering_room = State()


class SupportState(StatesGroup):
    waiting_message = State()
