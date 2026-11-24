"""购物车。"""
def add_item(cart=[], item=None):
    if item is None:
        return cart
    cart.append(item)
    return cart
