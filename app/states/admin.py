from aiogram.fsm.state import StatesGroup, State

class AdminAddProduct(StatesGroup):
    choosing_category = State()
    entering_name     = State()
    entering_price    = State()
    confirming        = State()

class AdminEditProduct(StatesGroup):
    choosing_product  = State()
    choosing_field    = State()
    entering_value    = State()

class AdminAddCategory(StatesGroup):
    entering_name     = State()
    choosing_parent   = State()   # родительская категория или "нет"
