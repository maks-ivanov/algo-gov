import algosdk
from math import sqrt

import pytest

from algosdk import account, encoding
from algosdk.logic import get_application_address

from gov.operations import (
    createAmmApp,
    setupAmmApp,
    supply,
    withdraw,
    marketSwap,
    closeAmm,
    optInToPoolToken,
)
from gov.util import getBalances, getAppGlobalState, getLastBlockTimestamp
from gov.testing.setup import getAlgodClient
from gov.testing.resources import getTemporaryAccount, optInToAsset, createDummyAsset


def is_close(a, b, e=1):
    return abs(a - b) <= e


def test_create():
    client = getAlgodClient()
    creator = getTemporaryAccount(client)

    tokenA = 1
    tokenB = 2
    minIncrement = 1000

    feeBps = -30
    with pytest.raises(OverflowError):
        createAmmApp(client, creator, tokenA, tokenB, feeBps, minIncrement)

    feeBps = 30
    appID = createAmmApp(client, creator, tokenA, tokenB, feeBps, minIncrement)

    actual = getAppGlobalState(client, appID)
    expected = {
        b"creator_key": encoding.decode_address(creator.getAddress()),
        b"token_a_key": tokenA,
        b"token_b_key": tokenB,
        b"fee_bps_key": feeBps,
        b"min_increment_key": minIncrement,
    }

    assert actual == expected


def test_setup():
    client = getAlgodClient()

    creator = getTemporaryAccount(client)
    funder = getTemporaryAccount(client)

    tokenAAmount = 1_000_000
    tokenBAmount = 2_000_000
    poolTokenAmount = 10 ** 13
    tokenA = createDummyAsset(client, tokenAAmount, funder)
    tokenB = createDummyAsset(client, tokenBAmount, funder)
    feeBps = 30
    minIncrement = 1000

    appID = createAmmApp(client, creator, tokenA, tokenB, feeBps, minIncrement)

    poolToken = setupAmmApp(
        client=client,
        appID=appID,
        funder=funder,
        tokenA=tokenA,
        tokenB=tokenB,
    )

    actualState = getAppGlobalState(client, appID)
    expectedState = {
        b"creator_key": encoding.decode_address(creator.getAddress()),
        b"token_a_key": tokenA,
        b"token_b_key": tokenB,
        b"pool_token_key": poolToken,
        b"fee_bps_key": feeBps,
        b"min_increment_key": minIncrement,
        b"pool_tokens_outstanding_key": 0,
    }

    assert actualState == expectedState

    actualBalances = getBalances(client, get_application_address(appID))
    expectedBalances = {0: 400_000, tokenA: 0, tokenB: 0, poolToken: poolTokenAmount}

    assert actualBalances == expectedBalances

    with pytest.raises(algosdk.error.AlgodHTTPError):
        # assert fail when trying to set up the same amm again
        setupAmmApp(
            client=client,
            appID=appID,
            funder=funder,
            tokenA=tokenA,
            tokenB=tokenB,
        )


def test_not_setup():
    client = getAlgodClient()
    creator = getTemporaryAccount(client)

    tokenA = 1
    tokenB = 2
    feeBps = 30
    minIncrement = 1000

    appID = createAmmApp(client, creator, tokenA, tokenB, feeBps, minIncrement)

    ops = [
        lambda: supply(client, appID, 10, 10, creator),
        lambda: withdraw(client, appID, 10, creator),
        lambda: marketSwap(client, appID, 10, tokenA, creator),
    ]

    for op in ops:
        with pytest.raises(AssertionError):
            op()

    closeAmm(client, appID, creator)


def test_supply():
    client = getAlgodClient()

    creator = getTemporaryAccount(client)

    tokenAAmount = 1_000_000
    tokenBAmount = 2_000_000
    tokenA = createDummyAsset(client, tokenAAmount, creator)
    tokenB = createDummyAsset(client, tokenBAmount, creator)
    feeBps = 30
    minIncrement = 1000

    appID = createAmmApp(client, creator, tokenA, tokenB, feeBps, minIncrement)

    poolToken = setupAmmApp(
        client=client,
        appID=appID,
        funder=creator,
        tokenA=tokenA,
        tokenB=tokenB,
    )

    optInToPoolToken(client, appID, creator)
    supply(client, appID, 1000, 2000, creator)
    actualTokensOutstanding = getAppGlobalState(client, appID)[
        b"pool_tokens_outstanding_key"
    ]
    expectedTokensOutstanding = int(sqrt(1000 * 2000))
    firstPoolTokens = getBalances(client, creator.getAddress())[poolToken]
    assert actualTokensOutstanding == expectedTokensOutstanding
    assert firstPoolTokens == expectedTokensOutstanding

    # should take 1000 : 2000 again
    supply(client, appID, 2000, 2000, creator)
    actualTokensOutstanding = getAppGlobalState(client, appID)[
        b"pool_tokens_outstanding_key"
    ]
    expectedTokensOutstanding = firstPoolTokens * 2
    secondPoolTokens = (
        getBalances(client, creator.getAddress())[poolToken] - firstPoolTokens
    )
    assert actualTokensOutstanding == expectedTokensOutstanding
    assert secondPoolTokens == firstPoolTokens

    # should take 10000 : 20000
    supply(client, appID, 12000, 20000, creator)
    actualTokensOutstanding = getAppGlobalState(client, appID)[
        b"pool_tokens_outstanding_key"
    ]
    expectedTokensOutstanding = firstPoolTokens * 12  # 2 + 10
    thirdPoolTokens = (
        getBalances(client, creator.getAddress())[poolToken]
        - secondPoolTokens
        - firstPoolTokens
    )
    assert actualTokensOutstanding == expectedTokensOutstanding
    assert thirdPoolTokens == firstPoolTokens * 10


def test_withdraw():
    client = getAlgodClient()
    creator = getTemporaryAccount(client)

    tokenAAmount = 1_000_000
    tokenBAmount = 2_000_000
    tokenA = createDummyAsset(client, tokenAAmount, creator)
    tokenB = createDummyAsset(client, tokenBAmount, creator)
    feeBps = 30
    minIncrement = 1000

    appID = createAmmApp(client, creator, tokenA, tokenB, feeBps, minIncrement)

    poolToken = setupAmmApp(
        client=client,
        appID=appID,
        funder=creator,
        tokenA=tokenA,
        tokenB=tokenB,
    )

    optInToPoolToken(client, appID, creator)
    supply(client, appID, 1000, 2000, creator)
    initialPoolTokensOutstanding = int(sqrt(1000 * 2000))

    # return one third of pool tokens to the pool, keep two thirds
    withdraw(client, appID, initialPoolTokensOutstanding // 3, creator)

    firstPoolTokens = getBalances(client, creator.getAddress())[poolToken]
    expectedPoolTokens = (
        initialPoolTokensOutstanding - initialPoolTokensOutstanding // 3
    )
    assert firstPoolTokens == expectedPoolTokens

    firstTokenAAmount = getBalances(client, creator.getAddress())[tokenA]
    expectedTokenAAmount = tokenAAmount - 1000 + 1000 // 3
    assert firstTokenAAmount == expectedTokenAAmount

    firstTokenBAmount = getBalances(client, creator.getAddress())[tokenB]
    expectedTokenBAmount = tokenBAmount - 2000 + 2000 // 3
    assert firstTokenBAmount == expectedTokenBAmount

    # double the original liquidity
    supply(client, appID, 1000 + 1000 // 3, 2000 + 2000 // 3, creator)
    actualTokensOutstanding = getAppGlobalState(client, appID)[
        b"pool_tokens_outstanding_key"
    ]
    assert is_close(actualTokensOutstanding, initialPoolTokensOutstanding * 2)

    withdraw(client, appID, initialPoolTokensOutstanding, creator)

    poolBalances = getBalances(client, get_application_address(appID))

    expectedTokenAAmount = 1000
    expectedTokenBAmount = 2000
    supplierPoolTokens = getBalances(client, creator.getAddress())[poolToken]
    assert is_close(poolBalances[tokenA], expectedTokenAAmount)
    assert is_close(poolBalances[tokenB], expectedTokenBAmount)
    assert is_close(supplierPoolTokens, initialPoolTokensOutstanding)


def test_swap():
    client = getAlgodClient()
    creator = getTemporaryAccount(client)
    tokenAAmount = 1_000_000_000
    tokenBAmount = 2_000_000_000
    tokenA = createDummyAsset(client, tokenAAmount, creator)
    tokenB = createDummyAsset(client, tokenBAmount, creator)
    feeBps = 30
    minIncrement = 1000

    appID = createAmmApp(client, creator, tokenA, tokenB, feeBps, minIncrement)

    poolToken = setupAmmApp(
        client=client,
        appID=appID,
        funder=creator,
        tokenA=tokenA,
        tokenB=tokenB,
    )

    optInToPoolToken(client, appID, creator)
    m, n = 100_000_000, 200_000_000
    supply(client, appID, m, n, creator)

    with pytest.raises(algosdk.error.AlgodHTTPError) as e:
        # swap wrong token
        marketSwap(client, appID, poolToken, 1, creator)
        assert "logic eval error: assert failed" in str(e)

    with pytest.raises(algosdk.error.AlgodHTTPError) as e:
        # swap too little
        marketSwap(client, appID, tokenA, 1, creator)
        assert "logic eval error: assert failed" in str(e)

    with pytest.raises(algosdk.error.AlgodHTTPError) as e:
        # swap more than in possession
        marketSwap(client, appID, tokenA, m * 10, creator)
        assert "logic eval error: assert failed" in str(e)

    x = 2_000_000
    marketSwap(client, appID, tokenA, x, creator)
    initialProduct = m * n
    expectedReceivedTokenB = n - initialProduct // (m + (100_00 - feeBps) * x // 100_00)

    poolBalances = getBalances(client, get_application_address(appID))
    actualReceivedTokenB = n - poolBalances[tokenB]
    actualSentTokenA = poolBalances[tokenA] - m
    assert actualSentTokenA == x
    assert actualReceivedTokenB == expectedReceivedTokenB

    expectedNewProduct = initialProduct - expectedReceivedTokenB * (m + x) + (x * n)
    actualNewProduct = poolBalances[tokenA] * poolBalances[tokenB]
    assert actualNewProduct == expectedNewProduct
    assert actualNewProduct > initialProduct

    mSecond, nSecond = poolBalances[tokenA], poolBalances[tokenB]
    y = x * 2
    marketSwap(client, appID, tokenB, y, creator)
    expectedReceivedTokenA = mSecond - actualNewProduct // (
        nSecond + (100_00 - feeBps) * y // 100_00
    )

    poolBalances = getBalances(client, get_application_address(appID))
    actualReceivedTokenA = mSecond - poolBalances[tokenA]
    actualSentTokenB = poolBalances[tokenB] - nSecond

    assert actualSentTokenB == y
    assert actualReceivedTokenA == expectedReceivedTokenA

    expectedNewProduct = (
        actualNewProduct - expectedReceivedTokenA * (nSecond + y) + (y * mSecond)
    )
    actualNewProduct = poolBalances[tokenA] * poolBalances[tokenB]
    assert actualNewProduct == expectedNewProduct
    assert actualNewProduct > initialProduct

    expectedRatio = (m + x - expectedReceivedTokenA) / (n - expectedReceivedTokenB + y)
    beforeWithdrawBalanceA = poolBalances[tokenA]
    beforeWithdrawBalanceB = poolBalances[tokenB]
    actualRatio = beforeWithdrawBalanceA / beforeWithdrawBalanceB
    assert actualRatio == expectedRatio

    toWithdraw = int(sqrt(initialProduct) // 2)
    withdraw(client, appID, toWithdraw, creator)
    poolBalances = getBalances(client, get_application_address(appID))
    afterWithdrawBalanceA = poolBalances[tokenA]
    afterWithdrawBalanceB = poolBalances[tokenB]
    actualRatio = afterWithdrawBalanceA / afterWithdrawBalanceB
    assert actualRatio == expectedRatio
    assert afterWithdrawBalanceA / beforeWithdrawBalanceA == 0.5
    assert afterWithdrawBalanceB / beforeWithdrawBalanceB == 0.5
