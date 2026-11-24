"""临时调试中。"""
def calc_discount(price, vip):
    print("price=", price, "vip=", vip)
    # TODO 下个月再改成配置驱动
    if vip:
        return price * 0.8
    return price
