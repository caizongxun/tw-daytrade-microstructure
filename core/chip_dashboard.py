# core/chip_dashboard.py
# 印出當前籌碼面板（給 paper mode 看狀態用）

from loguru import logger
from core.chip_signal import ChipSignalEngine


def print_chip_dashboard(symbol: str, chip_engine: ChipSignalEngine):
    result = chip_engine.get_chip_score(symbol)
    details = result.get('details', {})
    inst = details.get('institutional', {})
    margin = details.get('margin', {})
    whale = details.get('whale', {})
    futures = details.get('futures', {})
    lending = details.get('lending', {})

    print(f"\n{'='*55}")
    print(f"  籌碼面板 | {symbol}")
    print(f"{'='*55}")
    print(f"  綜合籌碼分數 : {result['chip_score']:+.3f}  ({'偏多' if result['chip_score'] > 0 else '偏空' if result['chip_score'] < 0 else '中性'})")
    print(f"{'-'*55}")
    print(f"  [外資期貨]  淨多單: {futures.get('foreign_futures_net_oi', 'N/A')}  "
          f"變化: {futures.get('foreign_futures_oi_change', 'N/A'):.0f}  "
          f"{'多' if futures.get('futures_signal', 0) > 0 else '空'}")
    print(f"  [三大法人]  分數: {result['institutional_score']:+.3f}  "
          f"外資: {inst.get('foreign', 0):.0f}  投信: {inst.get('trust', 0):.0f}  自營: {inst.get('dealer', 0):.0f}")
    print(f"  [集保大戶]  千張比: {whale.get('whale_pct', 0):.1f}%  "
          f"變化: {whale.get('whale_change', 0):+.2f}%  散戶比: {whale.get('retail_pct', 0):.1f}%")
    print(f"  [融資融券]  融資: {margin.get('margin_balance', 0):.0f}張  "
          f"3日變: {margin.get('margin_change_3d', 0):+.0f}  "
          f"券資比: {margin.get('short_to_margin_ratio', 0):.2%}")
    print(f"  [借  券]   餘額: {lending.get('lending_balance', 0):.0f}  "
          f"3日變: {lending.get('lending_change_3d', 0):+.0f}  "
          f"{'放空壓力' if lending.get('lending_signal', 0) < 0 else '正常'}")
    print(f"{'='*55}\n")
