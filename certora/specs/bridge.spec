////////////////////////////////////////////////////////////////////////////
//                       Imports and multi-contracts                      //
////////////////////////////////////////////////////////////////////////////
import "erc20.spec"

// Declaring aliases for contracts according to the format:
// using Target_Contract as Alias_Name
/************************
 *     L1 contracts     *
 ************************/
    using DummyERC20UnderlyingA_L1 as UNDERLYING_ASSET_A 
    using DummyERC20UnderlyingB_L1 as UNDERLYING_ASSET_B
    using ATokenWithPoolA_L1 as ATOKEN_A
    using ATokenWithPoolB_L1 as ATOKEN_B
    using DummyERC20RewardToken as REWARD_TOKEN
    using SymbolicLendingPoolL1 as LENDINGPOOL_L1
    using IncentivesControllerMock_L1 as incentivesController

/************************
 *     L2 contracts     *
 ************************/
    using BridgeL2Harness as BRIDGE_L2
    using StaticATokenA_L2 as STATIC_ATOKEN_A
    using StaticATokenB_L2 as STATIC_ATOKEN_B

// For referencing structs
    using BridgeHarness as Bridge

////////////////////////////////////////////////////////////////////////////
//                       Methods                                          //
////////////////////////////////////////////////////////////////////////////
// Declaring contracts' methods and summarizing them as needed
methods {
/**********************
 *     Bridge.sol     *
 **********************/
 // Note that some functions should only be called via BridgeHarness
 // e.g. withdraw(), invoked by the initiateWithdraw on L2.
    initialize(uint256, address, address, address[], uint256[])
    deposit(address, uint256, uint256, uint16, bool) returns (uint256) 
    withdraw(address, uint256, address, uint256, uint256, bool)
    updateL2State(address)
    receiveRewards(uint256, address, uint256)
    
/*************************
 *     BridgeHarness     *
 *************************/
    // Note that these methods take as args OR return the contract types that are written in comment to their right.
    // In CVL we contracts are addresses an therefore we demand return of an address
    getUnderlyingAssetOfAToken(address) returns (address) envfree //(IERC20)
    getATokenOfUnderlyingAsset(address, address) returns (address) envfree
    getLendingPoolOfAToken(address) returns (address) envfree //(ILendingPool)
    _staticToDynamicAmount_Wrapper(uint256, address, address) envfree //(ILendingPool)
    _dynamicToStaticAmount_Wrapper(uint256, address, address) envfree //(ILendingPool)
    _computeRewardsDiff_Wrapper(uint256, uint256, uint256) envfree
    _getCurrentRewardsIndex_Wrapper(address) returns (uint256) 
    initiateWithdraw_L2(address, uint256, address, bool)
    bridgeRewards_L2(address, uint256)
    underlyingtoAToken(address) returns (address) => DISPATCHER(true)

/******************************
 *     IStarknetMessaging     *
 ******************************/
    // The methods of Bridge.sol that call this contract are being overridden to bypass the messaging communication.
    // Instead, we modeled the L2 side in solidity and made direct calls between the sides.

/************************
 *     ILendingPool     *
 ************************/
    // The lending pool used in the contract is encapsulated within a struct in IBridge.sol.
    // We point to direct calls to these methods using dispatchers. 
    deposit(address, uint256, address, uint16) => DISPATCHER(true)
    withdraw(address, uint256, address) returns (uint256) => DISPATCHER(true)
    getReserveNormalizedIncome(address) returns (uint256) => DISPATCHER(true)
    LENDINGPOOL_L1.liquidityIndex() returns (uint256) envfree


/*************************************************
 *     IATokenWithPool + IScaledBalanceToken     *
 *************************************************/
    mint(address, uint256, uint256) returns (bool) => DISPATCHER(true)
    mint(address, uint256) returns (bool) => DISPATCHER(true)
    burn(address, address, uint256, uint256) => DISPATCHER(true)
    burn(address, uint256) returns (bool) => DISPATCHER(true)
    POOL() returns (address) => DISPATCHER(true)
    scaledTotalSupply() returns (uint256) => DISPATCHER(true)
    UNDERLYING_ASSET_ADDRESS() => DISPATCHER(true) 
    getIncentivesController() => NONDET

/************************************
 *     IncentivesControllerMock     *
 ************************************/
    _rewardToken() returns (address) envfree => DISPATCHER(true)
    DISTRIBUTION_END() returns (uint256) => CONSTANT
    getRewardsVault() returns (address) => DISPATCHER(true)
    getAssetData(address) returns (uint256, uint256, uint256) => DISPATCHER(true)
    // Note that the sender of the funds here is RewardsVault which is arbitrary by default.
    // If any rule that count on the reward token balance, calls this method a `require RewardsVault != to` make sense to add
    claimRewards(address[], uint256, address) returns (uint256) => DISPATCHER(true)
    
/***************************
 *     BridgeL2Harness     *
 ***************************/
    BRIDGE_L2.l2RewardsIndexSetter(uint256)
    BRIDGE_L2.deposit(address, uint256, address) 
    BRIDGE_L2.initiateWithdraw(address, uint256, address, address, bool) returns (uint256)
    BRIDGE_L2.bridgeRewards(address, address, uint256)
    BRIDGE_L2.claimRewards(address, address)
    BRIDGE_L2.l2RewardsIndex() returns (uint256) envfree
    BRIDGE_L2.getStaticATokenAddress(address) returns (address) envfree
    BRIDGE_L2.address2uint256(address) returns (uint256) envfree

/******************
 *     Tokens     *
 ******************/
    ATOKEN_A.getUnderlyingAsset() returns (address) envfree
    ATOKEN_B.getUnderlyingAsset() returns (address) envfree  
    claimRewards(address) returns (uint256) => DISPATCHER(true)
    getRewTokenAddress() returns (address) => rewardToken()
}

////////////////////////////////////////////////////////////////////////////
//                       Definitions                                      //
////////////////////////////////////////////////////////////////////////////

// Definition of RAY unit
definition RAY() returns uint256 = 10^27;

// The following definition shall be used later in some invariants,
// by filtering out the 'initialize' function.
definition excludeInitialize(method f) returns bool =
    f.selector != 
    initialize(uint256, address, address, address[], uint256[]).selector; 

////////////////////////////////////////////////////////////////////////////
//                       Rules                                            //
////////////////////////////////////////////////////////////////////////////

/*
    @Rule

    @Description:
        The balance of the recipient of a withdrawal increase by the deserved (dynamic) amount in either aToken or underlying, and in the reward token.

    @Formula:
        {

        }

        < call withdraw >
        
        {
            if toUnderlyingAsset:
                assert underlyingBalanceAfter == underlyingBalanceBefore + _staticToDynamicAmount_Wrapper(staticAmount, underlying, LENDINGPOOL)
            else:
                assert aTokenBalanceAfter == aTokenBalanceBefore + _staticToDynamicAmount_Wrapper(staticAmount, underlying, LENDINGPOOL)
            assert rewardTokenBalanceAfter == rewardTokenBalanceBefore + _computeRewardsDiff_Wrapper(staticAmount, l2RewardsIndex, _getCurrentRewardsIndex_Wrapper(e, aToken))
        }

    @Note:

    @Link:
*/

rule integrityOfWithdraw(method f, address recipient, address aToken){
    uint256 l2sender; bool toUnderlyingAsset;
    uint256 staticAmount; 
    env e; calldataarg args;
    address underlying;
    address static;
    uint256 l2RewardsIndex = BRIDGE_L2.l2RewardsIndex();
    setLinkage(underlying, aToken, STATIC_ATOKEN_A);
    requireValidUser(e.msg.sender);
    setUnderlyingAToken(aToken, underlying);
    requireValidTokens(underlying, aToken, STATIC_ATOKEN_A);
    requireInvariant ATokenAssetPair(underlying, aToken);
    require underlying != REWARD_TOKEN;
    uint256 underlyingBalanceBefore = tokenBalanceOf(e, underlying, recipient);
    uint256 aTokenBalanceBefore = tokenBalanceOf(e, aToken, recipient);
    uint256 rewardTokenBalanceBefore = tokenBalanceOf(e, REWARD_TOKEN, recipient);

    uint256 rewards = _computeRewardsDiff_Wrapper(staticAmount, l2RewardsIndex, _getCurrentRewardsIndex_Wrapper(e, aToken));
    uint256 gain = _staticToDynamicAmount_Wrapper(staticAmount, underlying, LENDINGPOOL_L1);

    initiateWithdraw_L2(e, aToken, staticAmount, recipient, toUnderlyingAsset);

    uint256 underlyingBalanceAfter = tokenBalanceOf(e, underlying, recipient);
    uint256 aTokenBalanceAfter = tokenBalanceOf(e, aToken, recipient);
    uint256 rewardTokenBalanceAfter = tokenBalanceOf(e, REWARD_TOKEN, recipient);

    if (toUnderlyingAsset){
        assert 
        (underlyingBalanceAfter == underlyingBalanceBefore + gain) &&
        (aTokenBalanceAfter == aTokenBalanceBefore);
    }
    else {
        assert 
        (aTokenBalanceAfter == aTokenBalanceBefore + gain) &&
        (underlyingBalanceAfter == underlyingBalanceBefore);

    }
    assert rewardTokenBalanceAfter == rewardTokenBalanceBefore + rewards;
}

/*
    @Rule

    @Description:
        Balance of underlying asset change iff deposit/withdraw was called 

    @Formula:
        {

        }
        < call any function >
        {
            underlyingBalanceAfter == underlyingBalanceBefore => < any function besides deposit or withdraw was called >
            < Neither deposit nor withdraw were called > => underlyingBalanceAfter == underlyingBalanceBefore
        }

    @Note:
        Although withdraw() shouldn't be called by an external user,
        it does change the underlying balance, therefore we include it 
        in the assert statement.
    @Link:
*/

rule balanceOfUnderlyingAssetChanged(method f, uint256 amount) {
    env e;    
    address asset;
    address AToken;
    address static;
    address recipient;
    address sender = e.msg.sender;
    tokenSelector(asset, AToken, static);
    setLinkage(asset, AToken, static);
    requireInvariant ATokenAssetPair(asset, AToken);
    require recipient != AToken && recipient != Bridge && recipient != BRIDGE_L2;
    require sender != AToken && sender != Bridge && sender != BRIDGE_L2;

    // Underlying asset balances of sender and recipient before call.
    uint256 senderBalanceU1 = tokenBalanceOf(e, asset, e.msg.sender);
    uint256 recipientBalanceU1 = tokenBalanceOf(e, asset, recipient);

    // Call any interface function 
    callFunctionSetParams(f, e, recipient, AToken, asset, amount, true);

    // Underlying asset balances of sender and recipient after call.
    uint256 senderBalanceU2 = tokenBalanceOf(e, asset, e.msg.sender);
    uint256 recipientBalanceU2 = tokenBalanceOf(e, asset, recipient);

    bool balancesChanged = 
        !(senderBalanceU2 == senderBalanceU1 && 
            recipientBalanceU1 == recipientBalanceU2);

    assert balancesChanged <=> amount !=0 &&
            (f.selector == deposit(address, uint256, uint256, uint16, bool).selector 
            ||
            f.selector == withdraw(address,uint256,address,uint256,uint256,bool).selector
            ||
            f.selector == initiateWithdraw_L2(address, uint256, address, bool).selector)
            , "balanceOf changed";
}


// Rule violation, check required:
// https://vaas-stg.certora.com/output/41958/6e479c078ba3ef87986c/?anonymousKey=74b8bd40ffa18ccdf3d77c2283e32d714218a029
rule depositWithdrawReversed(uint256 amount)
{
    env eB; env eF;
    address Atoken; // AAVE Token
    address asset;  // underlying asset
    address static = STATIC_ATOKEN_A; // staticAToken
    uint256 l2Recipient = BRIDGE_L2.address2uint256(eB.msg.sender);
    uint16 referralCode;
    bool fromUA; // from underlying asset
    bool toUA; // to underlying asset

    uint256 index_L1 = LENDINGPOOL_L1.liquidityIndex(); 
    uint256 index_L2 = BRIDGE_L2.l2RewardsIndex();

    setLinkage(asset, Atoken, static);
    tokenSelector(asset, Atoken, static);
    requireInvariant ATokenAssetPair(asset, Atoken);
    require eF.msg.sender == eB.msg.sender;
    requireRayIndex();
    requireValidUser(eF.msg.sender);

    uint256 balanceU1 = tokenBalanceOf(eB, asset, eB.msg.sender);
    uint256 balanceA1 = tokenBalanceOf(eB, Atoken, eB.msg.sender);
    uint256 balanceS1 = tokenBalanceOf(eB, static, eB.msg.sender);
        uint256 staticAmount = deposit(eB, Atoken, l2Recipient, amount, referralCode, fromUA);
    uint256 balanceU2 = tokenBalanceOf(eB, asset, eB.msg.sender);
    uint256 balanceA2 = tokenBalanceOf(eB, Atoken, eB.msg.sender);
    uint256 balanceS2 = tokenBalanceOf(eB, static, eB.msg.sender);
        initiateWithdraw_L2(eF, Atoken, staticAmount, eF.msg.sender, toUA);
    uint256 balanceU3 = tokenBalanceOf(eB, asset, eB.msg.sender);
    uint256 balanceA3 = tokenBalanceOf(eB, Atoken, eB.msg.sender);
    uint256 balanceS3 = tokenBalanceOf(eB, static, eB.msg.sender);
    
    assert balanceS1 == balanceS3;
    assert index_L1 == index_L2 && fromUA == toUA => 
        (balanceA1 == balanceA3 && balanceU1 == balanceU3);
}

// Checks that the transitions between static to dynamic are inverses.
// Verified
rule dynamicToStaticInversible1(uint256 amount)
{
    // We assume both indexes (L1,L2) are represented in Ray (1e27).
    requireRayIndex();
    address asset;
    uint256 dynm = _staticToDynamicAmount_Wrapper(amount, asset, LENDINGPOOL_L1);
    uint256 stat = _dynamicToStaticAmount_Wrapper(dynm, asset, LENDINGPOOL_L1);
    assert amount == stat;
}

// Violated
rule dynamicToStaticInversible2(uint256 amount)
{
    // We assume both indexes (L1,L2) are represented in Ray (1e27).
    requireRayIndex();
    address asset;
    uint256 stat = _dynamicToStaticAmount_Wrapper(amount, asset, LENDINGPOOL_L1);
    uint256 dynm = _staticToDynamicAmount_Wrapper(stat, asset, LENDINGPOOL_L1);
    assert amount == dynm;
}

// Check consistency of 'asset' being registered as the underlying
// token of 'AToken', both in the AToken contract, and also in the 
// mapping _aTokenData.
// We exclude the 'initialize' function since it is called only once
// in the code. 
invariant underlying2ATokenConsistency(address AToken, address asset)
     (asset !=0 <=> AToken !=0) 
     =>
     (getUnderlyingAssetOfAToken(AToken) == asset 
     <=>
     getUnderlyingAssetHelper(AToken) == asset)
     filtered{f-> excludeInitialize(f)}

// Check consistency of 'asset' being registered as the underlying
// token of 'AToken', and 'AToken' connected to 'asset' in the lending pool.
// We exclude the 'initialize' function since it is called only once
// in the code. 
invariant ATokenAssetPair(address asset, address AToken)
    (asset !=0 <=> AToken !=0) 
    =>
    (getUnderlyingAssetOfAToken(AToken) == asset 
    <=>
    getATokenOfUnderlyingAsset(LENDINGPOOL_L1, asset) == AToken)
    filtered{f-> excludeInitialize(f)}

// The aToken-asset pair should be correctly registered after calling
// initialize, right after the constructor.
// This is complementary to the two invariants above.
rule initializeIntegrity(address AToken, address asset)
{
    env e;
    calldataarg args;

    // Post-constructor conditions
    require getUnderlyingAssetOfAToken(AToken) == 0;
    require getUnderlyingAssetHelper(AToken) == 0;
    require getATokenOfUnderlyingAsset(LENDINGPOOL_L1, asset) == 0;
    
    initialize(e, args);

    assert (asset !=0 && AToken !=0) => (
        (getUnderlyingAssetOfAToken(AToken) == asset 
        <=>
        getUnderlyingAssetHelper(AToken) == asset)
     &&
        (getUnderlyingAssetOfAToken(AToken) == asset 
        <=>
        getATokenOfUnderlyingAsset(LENDINGPOOL_L1, asset) == AToken));
}
    
////////////////////////////////////////////////////////////////////////////
//                       Functions                                        //
////////////////////////////////////////////////////////////////////////////

// Selects specific instances for underlying asset, AToken and static tokens.
function tokenSelector(
    address asset, 
    address AToken, 
    address static){
    require asset == UNDERLYING_ASSET_A || asset == UNDERLYING_ASSET_B;
    require AToken == ATOKEN_A || AToken == ATOKEN_B;
    require static == STATIC_ATOKEN_A || static == STATIC_ATOKEN_B;
}

// By definition, the liquidity indexes are expressed in RAY units.
// Therefore they must be at least as large as RAY (assuming liquidity index > 1).
function requireRayIndex() {
    require LENDINGPOOL_L1.liquidityIndex() >= RAY();
    require BRIDGE_L2.l2RewardsIndex() >= RAY();
}

// Linking the instances of ERC20s and LendingPool 
// within the ATokenData struct to the corresponding symbolic contracts.
function setLinkage(
    address asset, 
    address AToken, 
    address static){
    // Setting the underlying token of the given AToken as either UNDERLYING_ASSET_A or UNDERLYING_ASSET_B
    require getUnderlyingAssetOfAToken(AToken) == asset;
    require getLendingPoolOfAToken(AToken) == LENDINGPOOL_L1;
    require BRIDGE_L2.getStaticATokenAddress(AToken) == static;
    setUnderlyingAToken(AToken, asset);
}

function setUnderlyingAToken(address AToken, address asset) {
    if (AToken == ATOKEN_A) {
        require ATOKEN_A.getUnderlyingAsset() == asset;
    }
    else if (AToken == ATOKEN_B) {
        require ATOKEN_B.getUnderlyingAsset() == asset;
    }
}

function getUnderlyingAssetHelper(address AToken) returns address {
    if (AToken == ATOKEN_A) {
        return ATOKEN_A.getUnderlyingAsset();
    }
    else if (AToken == ATOKEN_B) {
        return ATOKEN_B.getUnderlyingAsset();
    }
    return 0;
}

// Require the token trio (asset, Atoken, StaticAToken) to have
// distinct addresses.
function requireValidTokens(
    address asset, 
    address AToken, 
    address static){
        require asset != AToken &&
                AToken != static &&
                static != asset;
}

// Requirements for a "valid" user - exclude contracts addresses.
function requireValidUser(address user){
    require 
        user != Bridge &&
        user != BRIDGE_L2 &&
        user != UNDERLYING_ASSET_A &&
        user != UNDERLYING_ASSET_B &&
        user != ATOKEN_A &&
        user != ATOKEN_B &&
        user != STATIC_ATOKEN_A &&
        user != STATIC_ATOKEN_B &&
        user != REWARD_TOKEN &&
        user != LENDINGPOOL_L1 &&
        user != incentivesController;
}

// Returns the address of the reward token contract (used for summarization)
function rewardToken() returns address {
    return REWARD_TOKEN;
}

function callFunctionSetParams(
    method f, env e, address receiver,
    address aToken, address asset,
    uint256 amount, bool fromToUnderlyingAsset) returns uint256 {
    if (f.selector == initiateWithdraw_L2(address, uint256, address, bool).selector){
        return initiateWithdraw_L2(e, aToken, amount, receiver, fromToUnderlyingAsset); 
    }   
    else if (f.selector == deposit(address, uint256, uint256, uint16, bool).selector){
        uint256 l2Recipient = BRIDGE_L2.address2uint256(receiver);
        uint16 referralCode;
        return deposit(e, aToken, l2Recipient, amount, referralCode, fromToUnderlyingAsset);
    }
    else if (f.selector == bridgeRewards_L2(address, uint256).selector) {
        bridgeRewards_L2(e, receiver, amount);
        return 0;
    }
    else if (f.selector == withdraw(address, uint256, address, uint256, uint256, bool).selector) {
        uint256 l2sender;
        withdraw(e, aToken, l2sender, receiver, amount, BRIDGE_L2.l2RewardsIndex(), fromToUnderlyingAsset);
        return 0;
    }
    else {
        calldataarg args;
        f(e, args);
        return 0;
    }     
}