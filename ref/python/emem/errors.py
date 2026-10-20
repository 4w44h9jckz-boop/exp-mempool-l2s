"""Result codes. Names follow go-ethereum's error variables where one exists.

`docs/spec/01-nonce-pool.md`, `02-frame-pool.md`, `03-block-building.md`, `04-matcha.md`,
`05-aggregation.md` and `06-lucid.md` say which clause raises each.
"""

from __future__ import annotations

OK = "ok"

# Shared with go-ethereum
ErrAlreadyKnown = "ErrAlreadyKnown"
ErrTxTypeNotSupported = "ErrTxTypeNotSupported"
ErrOversizedData = "ErrOversizedData"
ErrInvalidChainId = "ErrInvalidChainId"
ErrMaxInitCodeSizeExceeded = "ErrMaxInitCodeSizeExceeded"
ErrGasLimitTooHigh = "ErrGasLimitTooHigh"
ErrNegativeValue = "ErrNegativeValue"
ErrGasLimit = "ErrGasLimit"
ErrTipAboveFeeCap = "ErrTipAboveFeeCap"
ErrInvalidSender = "ErrInvalidSender"
ErrNonceMax = "ErrNonceMax"
ErrIntrinsicGas = "ErrIntrinsicGas"
ErrFloorDataGas = "ErrFloorDataGas"
ErrTxGasPriceTooLow = "ErrTxGasPriceTooLow"
ErrEmptyAuthList = "ErrEmptyAuthList"
ErrNonceTooLow = "ErrNonceTooLow"
ErrNonceTooHigh = "ErrNonceTooHigh"
ErrInsufficientFunds = "ErrInsufficientFunds"
ErrOutOfOrderTxFromDelegated = "ErrOutOfOrderTxFromDelegated"
ErrInflightTxLimitReached = "ErrInflightTxLimitReached"
ErrAuthorityReserved = "ErrAuthorityReserved"
ErrAlreadyReserved = "ErrAlreadyReserved"
ErrUnderpriced = "ErrUnderpriced"
ErrTxPoolOverflow = "ErrTxPoolOverflow"
ErrFutureReplacePending = "ErrFutureReplacePending"
ErrReplaceUnderpriced = "ErrReplaceUnderpriced"
ErrFeeCapTooLow = "ErrFeeCapTooLow"

# This repository's, for the frame pool
ErrFrameMalformed = "ErrFrameMalformed"
ErrFrameExpiryNotFirst = "ErrFrameExpiryNotFirst"
ErrFrameNoPayer = "ErrFrameNoPayer"
ErrFrameAtomicInPrefix = "ErrFrameAtomicInPrefix"
ErrFrameUnrecognizedPrefix = "ErrFrameUnrecognizedPrefix"
ErrFrameVerifyAfterPrefix = "ErrFrameVerifyAfterPrefix"
ErrFrameVerifyGas = "ErrFrameVerifyGas"
ErrFrameVerifyStateGas = "ErrFrameVerifyStateGas"
ErrFrameExpired = "ErrFrameExpired"
ErrFramePrefixReverted = "ErrFramePrefixReverted"
ErrFrameMissingApprove = "ErrFrameMissingApprove"
ErrFrameDeployNoCode = "ErrFrameDeployNoCode"
ErrFrameBannedOpcode = "ErrFrameBannedOpcode"
ErrFrameStateWrite = "ErrFrameStateWrite"
ErrFrameStorageReadNonSender = "ErrFrameStorageReadNonSender"
ErrFrameCallTarget = "ErrFrameCallTarget"
ErrFramePayerExposure = "ErrFramePayerExposure"
ErrFramePaymasterBusy = "ErrFramePaymasterBusy"
ErrFrameSenderBusy = "ErrFrameSenderBusy"

# This repository's, for the MATCHA proposal (`docs/spec/04-matcha.md`)
ErrFrameInsufficientWidth = "ErrFrameInsufficientWidth"
ErrFrameLoadUnderpriced = "ErrFrameLoadUnderpriced"

# This repository's, for EIP-8288 aggregation (`docs/spec/05-aggregation.md`)
ErrDepFrameMalformed = "ErrDepFrameMalformed"
ErrFrameTooManyDeps = "ErrFrameTooManyDeps"
ErrFrameDepsUnproven = "ErrFrameDepsUnproven"
ErrWrapperMalformed = "ErrWrapperMalformed"
ErrWrapperUnknownTx = "ErrWrapperUnknownTx"
ErrWrapperDeps = "ErrWrapperDeps"
ErrWrapperTooManyDeps = "ErrWrapperTooManyDeps"
ErrWrapperProof = "ErrWrapperProof"
ErrExecutionReverted = "ErrExecutionReverted"  # go-ethereum's vm.ErrExecutionReverted; a BB-7 builder's refusal

# This repository's, for EIP-8272 recent roots (`docs/spec/08-recent-roots.md`)
ErrFrameRootPosition = "ErrFrameRootPosition"
ErrFrameRootFuture = "ErrFrameRootFuture"
ErrFrameRootExpired = "ErrFrameRootExpired"
ErrFrameRootUnknown = "ErrFrameRootUnknown"

# This repository's, for EIP-8266 expiring nonces (`docs/spec/09-expiring-nonces.md`)
ErrFrameExpiryMissing = "ErrFrameExpiryMissing"
ErrFrameExpiryTooFar = "ErrFrameExpiryTooFar"

# This repository's, for EIP-8184 sealed transactions (`docs/spec/06-lucid.md`)
ErrSTMalformed = "ErrSTMalformed"
ErrSTExceedsToB = "ErrSTExceedsToB"
ErrSTNotIncludable = "ErrSTNotIncludable"

# This repository's, for claim-gated admission (`docs/spec/10-claim-gated-admission.md`)
ErrClaimMissing = "ErrClaimMissing"
ErrClaimInvalid = "ErrClaimInvalid"
ErrClaimWrongSlot = "ErrClaimWrongSlot"
ErrClaimEpoch = "ErrClaimEpoch"
ErrProofUnsigned = "ErrProofUnsigned"
ErrSlotRefused = "ErrSlotRefused"
ErrClaimRefused = "ErrClaimRefused"
ErrClaimUsed = "ErrClaimUsed"
ErrClaimExpired = "ErrClaimExpired"
ErrRelayAggregate = "ErrRelayAggregate"

# This repository's, for ERC-8421's standard ruleset (`docs/spec/14-erc-8421.md`)
ErrFramePreVerifyNoCode = "ErrFramePreVerifyNoCode"
ErrFrameStrayDefault = "ErrFrameStrayDefault"
ErrEntityVerifyGas = "ErrEntityVerifyGas"
ErrFrameUnassignedOpcode = "ErrFrameUnassignedOpcode"
ErrFrameOutOfGasRevert = "ErrFrameOutOfGasRevert"
ErrFrameCreation = "ErrFrameCreation"
ErrFrameStorageAccess = "ErrFrameStorageAccess"
ErrNonceGap = "ErrNonceGap"
ErrNonceKeyLimit = "ErrNonceKeyLimit"
ErrSenderLimit = "ErrSenderLimit"
ErrEntityIsSender = "ErrEntityIsSender"
ErrLocalStorage = "ErrLocalStorage"
ErrEntityBanned = "ErrEntityBanned"
ErrEntityThrottled = "ErrEntityThrottled"
ErrSenderThrottled = "ErrSenderThrottled"
ErrPayerOpsAllowed = "ErrPayerOpsAllowed"


class TxError(Exception):
    """A rejection. The pools raise it internally and return its code from `add`."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


# docs/spec/11-surface.md: bytes that are not a frame transaction, blobs, and a client answer SF-4 cannot map
ErrFrameDecode = "ErrFrameDecode"
ErrFrameBlobs = "ErrFrameBlobs"
ErrFrameClientRefused = "ErrFrameClientRefused"
