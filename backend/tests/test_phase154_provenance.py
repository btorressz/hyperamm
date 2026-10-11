from datetime import timedelta
import pytest
from app.research_comparison.comparison import compare
from test_phase152_live_streams import streams
from phase154_helpers import request

async def test_stable_economic_identity_request_time_independent(streams):
    service,_,clock=streams
    snap=service.snapshot('BTC');a=compare(request(),snap,generated_at=clock())
    clock.advance(1);b=compare(request(),service.snapshot('BTC'),generated_at=clock())
    assert a.provenance.comparison_fingerprint==b.provenance.comparison_fingerprint and a.generated_at!=b.generated_at
    assert a.research.run_fingerprint==request().research.run_fingerprint
    assert a.provenance.observer_instance_id==service.instance_id
    assert a.provenance.l2_source_timestamp==snap.order_book.source_timestamp
    assert a.provenance.perp_observed_at==snap.perp_context.observed_at and a.provenance.perp_event_time=='UNKNOWN'
    assert a.provenance.research_trust=='STRUCTURALLY_VALIDATED_CLIENT_SUPPLIED_NOT_AUTHENTICATED'
    assert a.provenance.research_frame_timestamp!=a.provenance.l2_source_timestamp
    clock.advance(60);c=compare(request(),service.snapshot('BTC'))
    assert c.provenance.comparison_fingerprint!=a.provenance.comparison_fingerprint
    assert a.provenance.l2_source_timestamp==c.provenance.l2_source_timestamp
    assert all(m.absolute_difference is None for m in c.metrics)

@pytest.mark.parametrize('changed',['observer','generation','research_run','context_receipt','book_value'])
async def test_material_evidence_changes_fingerprint(streams,changed):
    service,_,clock=streams;snap=service.snapshot('BTC');body=request();a=compare(body,snap)
    data=snap.model_dump()
    if changed=='observer':data['status']['observer_instance_id']='00000000-0000-0000-0000-000000000001'
    if changed=='generation':data['status']['connection_generation']+=1
    if changed=='context_receipt':
        stamp=data['perp_context']['observed_at']+timedelta(milliseconds=1)
        data['perp_context']['observed_at']=stamp;data['status']['last_perp_observed_at']=stamp
    if changed=='research_run':body=body.model_copy(update={'research':body.research.model_copy(update={'run_fingerprint':'c'*64})})
    if changed=='book_value':data['order_book']['bids'][0]['size']+=1
    b=compare(body,type(snap).model_validate(data))
    assert a.provenance.comparison_fingerprint!=b.provenance.comparison_fingerprint
