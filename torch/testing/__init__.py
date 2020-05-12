"""
The testing package contains testing-specific utilities.
"""

import torch
import random

FileCheck = torch._C.FileCheck

__all__ = [
    'assert_allclose', 'make_non_contiguous', 'rand_like', 'randn_like'
]

rand_like = torch.rand_like
randn_like = torch.randn_like


def assert_allclose(actual, expected, rtol=None, atol=None, equal_nan=True, msg=''):
    if not isinstance(actual, torch.Tensor):
        actual = torch.tensor(actual)
    if not isinstance(expected, torch.Tensor):
        expected = torch.tensor(expected, dtype=actual.dtype)
    if expected.shape != actual.shape:
        expected = expected.expand_as(actual)
    if rtol is None or atol is None:
        if rtol is not None or atol is not None:
            raise ValueError("rtol and atol must both be specified or both be unspecified")
        rtol, atol = _get_default_tolerance(actual, expected)

    close = torch.isclose(actual, expected, rtol, atol, equal_nan)
    if close.all():
        return

    # Find the worst offender
    error = (expected - actual).abs()
    expected_error = atol + rtol * expected.abs()
    delta = error - expected_error
    delta[close] = 0  # mask out NaN/inf
    _, index = delta.reshape(-1).max(0)

    # TODO: consider adding torch.unravel_index
    def _unravel_index(index, shape):
        res = []
        for size in shape[::-1]:
            res.append(int(index % size))
            index = int(index // size)
        return tuple(res[::-1])

    index = _unravel_index(index.item(), actual.shape)

    # Count number of offenders
    count = (~close).long().sum()
    if msg == '' or msg is None:
        msg = ('Not within tolerance rtol={} atol={} at input{} ({} vs. {}) and {}'
               ' other locations ({:2.2f}%)')
        msg = msg.format(
            rtol, atol, list(index), actual[index].item(), expected[index].item(),
            count - 1, 100 * count / actual.numel())

    raise AssertionError(msg)

def make_non_contiguous(tensor):
    if tensor.numel() <= 1:  # can't make non-contiguous
        return tensor.clone()
    osize = list(tensor.size())

    # randomly inflate a few dimensions in osize
    for _ in range(2):
        dim = random.randint(0, len(osize) - 1)
        add = random.randint(4, 15)
        osize[dim] = osize[dim] + add

    # narrow doesn't make a non-contiguous tensor if we only narrow the 0-th dimension,
    # (which will always happen with a 1-dimensional tensor), so let's make a new
    # right-most dimension and cut it off

    input = tensor.new(torch.Size(osize + [random.randint(2, 3)]))
    input = input.select(len(input.size()) - 1, random.randint(0, 1))
    # now extract the input of correct size from 'input'
    for i in range(len(osize)):
        if input.size(i) != tensor.size(i):
            bounds = random.randint(1, input.size(i) - tensor.size(i))
            input = input.narrow(i, bounds, tensor.size(i))

    input.copy_(tensor)

    # Use .data here to hide the view relation between input and other temporary Tensors
    return input.data


def get_all_dtypes(include_half=True, include_bfloat16=True, include_bool=True, include_complex=True):
    dtypes = get_all_int_dtypes() + get_all_fp_dtypes(include_half=include_half, include_bfloat16=include_bfloat16)
    if include_bool:
        dtypes.append(torch.bool)
    if include_complex:
        dtypes += get_all_complex_dtypes()
    return dtypes

def get_all_math_dtypes(device):
    return get_all_int_dtypes() + get_all_fp_dtypes(include_half=device.startswith('cuda'), include_bfloat16=False) + get_all_complex_dtypes()

def get_all_complex_dtypes():
    return [torch.complex64, torch.complex128]

def get_all_int_dtypes():
    return [torch.uint8, torch.int8, torch.int16, torch.int32, torch.int64]

def get_all_fp_dtypes(include_half=True, include_bfloat16=True):
    dtypes = [torch.float32, torch.float64]
    if include_half:
        dtypes.append(torch.float16)
    if include_bfloat16:
        dtypes.append(torch.bfloat16)
    return dtypes

def get_all_device_types():
    return ['cpu'] if not torch.cuda.is_available() else ['cpu', 'cuda']

# 'dtype': (rtol, atol)
_default_tolerances = {
    'float64': (1e-5, 1e-8),  # NumPy default
    'float32': (1e-4, 1e-5),  # This may need to be changed
    'float16': (1e-3, 1e-3),  # This may need to be changed
}


def _get_default_tolerance(a, b=None):
    if b is None:
        dtype = str(a.dtype).split('.')[-1]  # e.g. "float32"
        return _default_tolerances.get(dtype, (0, 0))
    a_tol = _get_default_tolerance(a)
    b_tol = _get_default_tolerance(b)
    return (max(a_tol[0], b_tol[0]), max(a_tol[1], b_tol[1]))
