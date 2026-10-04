from decimal import Decimal
import pytest
from app.amm.constant_product import invariant, marginal_price, simulate_base_to_quote, simulate_quote_to_base
from app.amm.virtual_reserves import initialize_virtual_pool, recenter_pool
from app.amm.liquidity_curve import sample_curve
from app.amm.discretizer import compile_quotes, normalize_price, normalize_size
from app.amm.models import AmmModel
from app.amm.concentrated import concentrated_weights

D=Decimal

def pool(): return initialize_virtual_pool(D('100'),D('300000'))

def test_constant_product_invariant(): assert invariant(D('100'),D('300000')) == D('30000000')
def test_marginal_price(): assert marginal_price(pool()) == D('3000')
def test_virtual_swap_base_to_quote_preserves_k():
    p,out=simulate_base_to_quote(pool(),D('1')); assert p.reserve_base*p.reserve_quote == p.k and out>0
def test_virtual_swap_quote_to_base_preserves_k():
    p,out=simulate_quote_to_base(pool(),D('3000')); assert p.reserve_base*p.reserve_quote == p.k and out>0
def test_invalid_reserves_rejected():
    with pytest.raises(ValueError): initialize_virtual_pool(D('0'),D('1'))
def test_recenter_preserves_k_and_price():
    p=recenter_pool(pool(),D('3200')); assert p.k==pool().k and abs(marginal_price(p)-D('3200')) < D('1e-20')
def test_curve_sampling_deterministic():
    a=sample_curve(pool(),D('3000'),4,D('100')); b=sample_curve(pool(),D('3000'),4,D('100')); assert a==b
def test_concentrated_weights_normalize():
    w=concentrated_weights([D('10'),D('50'),D('100')],D('8'),D('10'),D('200')); assert abs(sum(w)-D('1'))<D('1e-24')
def test_concentration_factor_allocates_more_near():
    ds=[D('10'),D('50'),D('100'),D('200')]
    low=concentrated_weights(ds,D('1'),D('10'),D('200'))
    high=concentrated_weights(ds,D('20'),D('10'),D('200'))
    assert high[0] > low[0] and high[-1] < low[-1]
def test_bid_ask_ordering_no_cross_and_positive():
    q=compile_quotes(pool(),D('3000'),AmmModel.CONSTANT_PRODUCT,6,D('100'),D('6'),D('0.1'),4)
    bids=[x for x in q if x.side=='BID']; asks=[x for x in q if x.side=='ASK']
    assert bids==sorted(bids,key=lambda x:x.price,reverse=True)
    assert asks==sorted(asks,key=lambda x:x.price)
    assert bids[0].price < asks[0].price
    assert all(x.price>0 and x.size>0 for x in q)
def test_tick_normalization():
    assert normalize_price(D('3000.09'),D('0.1'),'BID')==D('3000.0')
    assert normalize_price(D('3000.01'),D('0.1'),'ASK')==D('3000.1')
def test_size_normalization(): assert normalize_size(D('1.23459'),3)==D('1.234')
def test_quote_generation_deterministic():
    args=(pool(),D('3000'),AmmModel.CONCENTRATED,6,D('100'),D('6'),D('0.1'),4,D('8'),D('10'),D('200'))
    assert compile_quotes(*args)==compile_quotes(*args)

def test_base_order_size_and_total_liquidity_are_enforced():
    q=compile_quotes(pool(),D('3000'),AmmModel.CONCENTRATED,4,D('100'),D('2.0'),D('0.1'),4,D('8'),D('10'),D('200'),D('0.2'))
    bids=[x for x in q if x.side=='BID']
    assert all(x.size >= D('0.2') for x in bids)
    assert sum((x.size for x in bids),D('0')) <= D('2.0')
