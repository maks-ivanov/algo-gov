from time import time, sleep

from algosdk import account, encoding
from algosdk.logic import get_application_address
from gov.operations import (
    createGovernor,
    setupGovernor,
    stake,
    optInToApp,
    sendToken,
    delegateVotingPower,
    createProposal,
    registerProposal,
    activateProposal,
    vote,
    executeProposal,
    claim,
    beginNewGovernanceCycle,
)
from gov.util import (
    getBalances,
    getUserLocalState,
    getAppGlobalState,
    getLastBlockTimestamp,
)
from gov.testing.setup import getAlgodClient
from gov.testing.resources import (
    getTemporaryAccount,
    optInToAsset,
    createDummyAsset,
)


def simple_gov():
    client = getAlgodClient()

    print("Alice is generating temporary accounts...")
    creator = getTemporaryAccount(client)  # voter 0
    acct1 = getTemporaryAccount(client)  # voter 1
    acct2 = getTemporaryAccount(client)  # voter 2
    acct3 = getTemporaryAccount(client)  # proposal creator
    acct4 = getTemporaryAccount(client)  # target

    print("Alice is generating example tokens...")
    govTokenAmount = 10 ** 13
    govToken = createDummyAsset(client, govTokenAmount, creator)
    print("Gov token id is:", govToken)
    optInToAsset(client, govToken, acct1)
    print("Alice is creating a governor contract...")
    governorAppId = createGovernor(
        client=client,
        creator=creator,
        govTokenId=govToken,
        proposeThreshold=5,
        voteThreshold=1,
        quorumThreshold=20,
        stakeDurationSeconds=301,
        proposeDurationSeconds=100,
        voteDurationSeconds=100,
        executeDelaySeconds=50,
        claimDurationSeconds=100,
    )

    print("acct3 is creating a proposal contract that pays to acct4...")
    proposalAppId = createProposal(
        client=client, creator=acct3, governorId=governorAppId, targetId=acct4
    )

    print("Proposal id", proposalAppId)
    print(getAppGlobalState(client, proposalAppId))

    setupGovernor(client, governorAppId, creator, govToken)  # 0
    t0 = getLastBlockTimestamp(client)[1]
    print("Alice is staking gov token for votes")
    optInToApp(client, governorAppId, creator)  # 50
    stake(client, governorAppId, 10, creator)  # 100
    sendToken(client, creator, govToken, 1000, acct1)  # 150

    print("Charlie is staking gov token for votes")
    optInToApp(client, governorAppId, acct1)  # 200
    stake(client, governorAppId, 15, acct1)  # 250
    print("Alice's voting info:", getUserLocalState(client, creator))
    print("Charlie's voting info:", getUserLocalState(client, acct1))

    print("Charlie is delegating his votes to Alice")
    print("t+", getLastBlockTimestamp(client)[1] - t0)
    delegateVotingPower(client, governorAppId, acct1, creator)  # 300
    print("Alice's voting info:", getUserLocalState(client, creator))
    print("Charlie's voting info:", getUserLocalState(client, acct1))
    print("t+", getLastBlockTimestamp(client)[1] - t0)

    # point governor to proposal
    registerProposal(client, governorAppId, proposalAppId, creator)
    print("t+", getLastBlockTimestamp(client)[1] - t0)
    print(getAppGlobalState(client, governorAppId))
    # point proposal to governor and enable voting
    activateProposal(client, proposalAppId, governorAppId, 0, acct4)
    print("t+", getLastBlockTimestamp(client)[1] - t0)
    print(getAppGlobalState(client, proposalAppId))

    vote(client, governorAppId, proposalAppId, 1, creator)
    print(getAppGlobalState(client, governorAppId))
    print("t+", getLastBlockTimestamp(client)[1] - t0)

    for _ in range(2):  # hack to tick time faster
        sendToken(client, creator, govToken, 1, acct1)

    print("t+", getLastBlockTimestamp(client)[1] - t0)

    target = encoding.encode_address(
        getAppGlobalState(client, proposalAppId)[b"target_id_key"]
    )
    targetBalance = getBalances(client, target)
    proposalBalance = getBalances(client, get_application_address(proposalAppId))

    print(proposalBalance)
    print(targetBalance)

    executeProposal(client, governorAppId, proposalAppId, creator)
    print(getAppGlobalState(client, governorAppId))
    print(" ")
    targetBalance = getBalances(client, target)
    proposalBalance = getBalances(client, get_application_address(proposalAppId))
    # at this point proposal should have paid out 1000 microalgos to target
    print(proposalBalance)
    print(targetBalance)
    print("t+", getLastBlockTimestamp(client)[1] - t0)

    claim(client, governorAppId, acct1)
    beginNewGovernanceCycle(client, governorAppId, creator)


simple_gov()
