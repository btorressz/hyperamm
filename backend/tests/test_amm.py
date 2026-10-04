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

@pytest.mark.parametrize('side',['BID','ASK'])
def test_successive_reserve_deltas_drive_weights_and_sizes(side):
    # Deliberately unrecentered input: origin must still be the fair-value state.
    fair=D('3200')
    points=[p for p in sample_curve(pool(),fair,4,D('1000')) if p.side==side]
    previous=(pool().k/fair).sqrt()
    cumulative=D('0')
    for point in points:
        assert point.target_base==(pool().k/point.price).sqrt()
        delta=abs(point.target_base-previous)
        assert point.incremental_base==delta
        assert delta.is_finite() and delta>0
        assert point.cumulative_base > cumulative
        assert point.cumulative_base-cumulative==delta
        previous=point.target_base; cumulative=point.cumulative_base
    total=sum(p.incremental_base for p in points)
    assert all(p.weight==p.incremental_base/total for p in points)
    assert len({p.weight for p in points})>1
    quotes=[q for q in compile_quotes(pool(),fair,AmmModel.CONSTANT_PRODUCT,4,D('1000'),D('2'),D('.1'),6,base_order_size=D('.1')) if q.side==side]
    assert [q.size for q in quotes]==[normalize_size(D('.1')+D('1.6')*p.weight,6) for p in points]
    assert len({q.size for q in quotes})>1

@pytest.mark.parametrize('side',['BID','ASK'])
def test_concentration_multiplies_amm_profile(side):
    def sampled(model,c):
        return [p for p in sample_curve(pool(),D('3000'),4,D('200'),model,D(c)) if p.side==side]
    natural=sampled(AmmModel.CONSTANT_PRODUCT,'0')
    concentrated=sampled(AmmModel.CONCENTRATED,'20')
    neutral=sampled(AmmModel.CONCENTRATED,'0')
    factors=concentrated_weights([p.distance_bps for p in natural],D('20'),D('10'),D('200'))
    raw=[p.incremental_base*f for p,f in zip(natural,factors)]
    assert [p.weight for p in concentrated]==[v/sum(raw) for v in raw]
    assert abs(sum(p.weight for p in concentrated)-1)<D('1e-24')
    assert concentrated[0].weight>natural[0].weight
    assert concentrated[-1].weight<natural[-1].weight
    assert all(abs(a.weight-b.weight)<D('1e-24') for a,b in zip(natural,neutral))

@pytest.mark.parametrize('model',list(AmmModel))
@pytest.mark.parametrize('precision',[2,4,8])
def test_budget_baseline_finite_and_deterministic_after_rounding(model,precision):
    args=(pool(),D('3000'),model,6,D('200'),D('2'),D('.1'),precision)
    quotes=compile_quotes(*args,concentration_factor=D('20'),base_order_size=D('.10001'))
    assert quotes==compile_quotes(*args,concentration_factor=D('20'),base_order_size=D('.10001'))
    assert all(q.price.is_finite() and q.price>0 and q.size.is_finite() and q.size>=D('.10001') for q in quotes)
    for side in ('BID','ASK'):
        assert sum(q.size for q in quotes if q.side==side)<=D('2')

def test_unrepresentable_baseline_budget_refused():
    with pytest.raises(ValueError,match='cover'):
        compile_quotes(pool(),D('3000'),AmmModel.CONSTANT_PRODUCT,4,D('100'),D('.40004'),D('.1'),2,base_order_size=D('.10001'))
