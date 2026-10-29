from phase155b_soak_runner import run_soak

async def test_bounded_soak_reconnects_all_markets_and_releases_resources():
    result=await run_soak(.5,3)
    assert result['classification']=='PASS' and result['cycles_completed']>=1
    assert result['dropped_events']>0 and result['retired_callback_attempts']>=3
    assert result['maximum_observed_queue_size']==8
    assert result['subscriber_count_after_shutdown']==result['remaining_owned_tasks']==result['remaining_owned_threads']==0
