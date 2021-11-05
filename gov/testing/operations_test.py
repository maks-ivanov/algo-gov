import algosdk
import pytest
from algosdk import encoding

from gov.operations import createGovernor, setupGovernor, delegateVotingPower, stake, delegatePropositionPower, \
    registerProposal, vote, beginNewGovernanceCycle, claim, executeProposal
from gov.testing.resources import getTemporaryAccount, createDummyAsset, optInToAsset
from gov.testing.setup import getAlgodClient
from gov.util import getAppGlobalState, getLastBlockTimestamp


def is_close(a, b, e=1):
    return abs(a - b) <= e


def equal_dicts(d1, d2, ignore_keys):
    d1_filtered = {k:v for k,v in d1.items() if k not in ignore_keys}
    d2_filtered = {k:v for k,v in d2.items() if k not in ignore_keys}
    return d1_filtered == d2_filtered

def test_create():
    client = getAlgodClient()
    creator = getTemporaryAccount(client)
    govTokenAmount = 10 ** 13
    govToken = createDummyAsset(client, govTokenAmount, creator)
    print("Alice is creating a governor contract...")
    governorAppId = createGovernor(
        client=client,
        creator=creator,
        govTokenId=govToken,
        proposeThreshold=5,
        voteThreshold=1,
        quorumThreshold=20,
        stakeDurationSeconds=300,
        proposeDurationSeconds=100,
        voteDurationSeconds=100,
        executeDelaySeconds=50,
        claimDurationSeconds=100,
    )

    actual = getAppGlobalState(client, governorAppId)
    expected = {
        b'vote_threshold_key': 1,
        b'creator_key': encoding.decode_address(creator.getAddress()),
        b'quorum_threshold_key': 20,
        b'max_num_proposals_key': 5,
        b'num_active_proposals_key': 0,
        b'propose_period_duration_key': 100,
        b'propose_threshold_key': 5,
        b'stake_period_duration_key': 300,
        b'gov_token_key': govToken,
        b'claim_period_duration_key': 100,
        b'execute_delay_duration_key': 50,
        b'vote_period_duration_key': 100
    }

    assert actual == expected

    # all of these should fail
    ops = [
        lambda: stake(client, governorAppId, 5, creator),
        lambda: delegateVotingPower(client, governorAppId, getTemporaryAccount(client), creator),
        lambda: delegatePropositionPower(client, governorAppId, getTemporaryAccount(client), creator),
        lambda: registerProposal(client, governorAppId, 123, creator),
        lambda: vote(client, governorAppId, 123, 1, creator),
        lambda: executeProposal(client, governorAppId, 345, creator),
        lambda: claim(client, governorAppId, creator),
        lambda: beginNewGovernanceCycle(client, governorAppId, creator)
    ]

    for i in range(len(ops)):
        with pytest.raises(Exception):
            print(i)
            op = ops[i]
            op()


def test_setup():
    client = getAlgodClient()
    creator = getTemporaryAccount(client)
    govTokenAmount = 10 ** 13
    govToken = createDummyAsset(client, govTokenAmount, creator)
    print("Alice is creating a governor contract...")
    governorAppId = createGovernor(
        client=client,
        creator=creator,
        govTokenId=govToken,
        proposeThreshold=5,
        voteThreshold=1,
        quorumThreshold=20,
        stakeDurationSeconds=300,
        proposeDurationSeconds=100,
        voteDurationSeconds=100,
        executeDelaySeconds=50,
        claimDurationSeconds=100,
    )

    startTime = getLastBlockTimestamp(client)[1] + 4 # add one block time (avg 4.5 s) for fund txn
    setupGovernor(client, governorAppId, creator, govToken)

    actual = getAppGlobalState(client, governorAppId)
    expected = {
        b'vote_threshold_key': 1,
        b'creator_key': encoding.decode_address(creator.getAddress()),
        b'quorum_threshold_key': 20,
        b'max_num_proposals_key': 5,
        b'num_active_proposals_key': 0,
        b'propose_period_duration_key': 100,
        b'propose_threshold_key': 5,
        b'stake_period_duration_key': 300,
        b'gov_token_key': govToken,
        b'claim_period_duration_key': 100,
        b'execute_delay_duration_key': 50,
        b'vote_period_duration_key': 100,
        b'start_time_key': startTime,
        b'gov_cycle_id_key': 0
    }

    assert equal_dicts(actual, expected, set(b'start_time_key')) # start time can be +-1
    assert is_close(actual[b'start_time_key'], expected[b'start_time_key'], e=1)

    # all of these should fail
    ops = [
        lambda: setupGovernor(client, governorAppId, creator, govToken),
        lambda: delegateVotingPower(client, governorAppId, getTemporaryAccount(client), creator),
        lambda: delegatePropositionPower(client, governorAppId, getTemporaryAccount(client), creator),
        lambda: registerProposal(client, governorAppId, 123, creator),
        lambda: vote(client, governorAppId, 123, 1, creator),
        lambda: executeProposal(client, governorAppId, 345, creator),
        lambda: claim(client, governorAppId, creator),
        lambda: beginNewGovernanceCycle(client, governorAppId, creator)
    ]

    for op in ops:
        with pytest.raises(algosdk.error.AlgodHTTPError):
            op()

