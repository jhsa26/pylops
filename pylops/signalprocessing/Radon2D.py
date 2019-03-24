import logging
import numpy as np
from pylops.basicoperators import Spread

logging.basicConfig(format='%(levelname)s: %(message)s', level=logging.WARNING)

def _linear(x, t, px):
    return t + px*x

def _parabolic(x, t, px):
    return t + px*x**2

def _hyperbolic(x, t, px):
    return np.sqrt(t**2 + (x/px)**2)

def _indices_2d(f, x, px, it, nt, interp=True):
    """Compute time and space indices of parametric line in ``f`` function

    Parameters
    ----------
    f : :obj:`func`
        Function computing values of parametric line for stacking
    x : :obj:`np.ndarray`
        Spatial axis (must be symmetrical around 0 and with sampling 1)
    px : :obj:`float`
        Slowness/curvature
    it : :obj:`int`
        Index of time axis
    nt : :obj:`int`
        Size scaof time axis
    interp : :obj:`bool`, optional
        Apply linear interpolation (``True``) or nearest interpolation
        (``False``) during stacking/spreading along parametric curve

    Returns
    -------
    xscan : :obj:`np.ndarray`
        Spatial indices
    tscan : :obj:`np.ndarray`
        Time indices
    dtscan : :obj:`np.ndarray`
        Decimal time variations for interpolation

    """
    tdecscan = f(x, it, px)
    if not interp:
        xscan = (tdecscan >= 0) & (tdecscan < nt)
    else:
        xscan = (tdecscan >= 0) & (tdecscan < nt - 1)
    tscan = tdecscan[xscan].astype(np.int)
    if interp:
        dtscan = tdecscan[xscan] - tscan
    else:
        dtscan = None
    return xscan, tscan, dtscan

def _indices_2d_onthefly(f, x, px, ip, it, nt, interp=True):
    """Wrapper around _indices_2d to allow on-the-fly computation of
    parametric curves"""
    return _indices_2d(f, x, px[ip], it, nt, interp=interp)


def Radon2D(taxis, haxis, pxaxis, kind='linear', centeredh=True,
            interp=True, onthefly=False, engine='numpy', dtype='float64'):
    r"""Two dimensional Radon transform.

    Apply two dimensional Radon forward (and adjoint) transform to a
    2-dimensional array of size :math:`[n_{px} \times n_t]`
    (and :math:`[n_x \times n_t]`).

    In forward mode this entails to spreading the model vector
    along parametric curves (lines, parabolas, or hyperbolas depending on the
    choice of ``kind``), while  stacking values in the data vector
    along the same parametric curves is performed in adjoint mode.

    Parameters
    ----------
    taxis : :obj:`np.ndarray`
        Time axis
    haxis : :obj:`np.ndarray`
        Spatial axis
    pxaxis : :obj:`np.ndarray`
        Axis of scanning variable :math:`p_x` of parametric curve
    kind : :obj:`str`, optional
        Curve to be used for stacking/spreading (``linear``, ``parabolic``,
        and ``hyperbolic`` are currently supported)
    centeredh : :obj:`bool`, optional
        Assume centered spatial axis (``True``) or not (``False``)
    interp : :obj:`bool`, optional
        Apply linear interpolation (``True``) or nearest interpolation
        (``False``) during stacking/spreading along parametric curve
    onthefly : :obj:`bool`, optional
        Compute stacking parametric curves on-the-fly as part of forward
        and adjoint modelling (``True``) or at initialization and store them
        in look-up table (``False``). Using a look-up table is computationally
        more efficient but increases the memory burden
    engine : :obj:`str`, optional
        Engine used for fft computation (``numpy`` or ``numba``). Note that
        ``numba`` can only be used when providing a look-up table
    dtype : :obj:`str`, optional
        Type of elements in input array.

    Returns
    -------
    r2op : :obj:`pylops.LinearOperator`
        Radon operator

    Raises
    ------
    NotImplementedError
        If ``kind`` is not ``linear``, ``parabolic``, or ``hyperbolic``

    See Also
    --------
    pylops.Spread: Spread operator

    Notes
    -----
    The Radon2D operator applies the following linear transform in adjoint mode
    to the data after reshaping it into a 2-dimensional array of
    size :math:`[n_x \times n_t]` in adjoint mode:

    .. math::
        m(p_x, t_0) = \int{d(x, t = f(p_x, x, t))} dx

    where :math:`f(p_x, x, t) = t_0 + p_x * x` where
    :math:`p_x = sin( \theta)/v` in linear mode,
    :math:`f(p_x, x, t) = t_0 + p_x * x^2` in parabolic mode, and
    :math:`f(p_x, x, t) = \sqrt{t_0^2 + x^2 / p_x^2}` in hyperbolic mode.

    As the adjoint operator can be interpreted as a repeated summation of sets
    of elements of the model vector along chosen parametric curves, the
    forward is implemented as spreading of values in the data vector along the
    same parametric curves. This operator is actually a thin wrapper around
    the :class:`pylops.Spread` operator.
    """
    # axes
    nt, nh, npx = taxis.size, haxis.size, pxaxis.size
    if kind == 'linear':
        f = _linear
    elif kind == 'parabolic':
        f = _parabolic
    elif kind == 'hyperbolic':
        f = _hyperbolic
    else:
        raise NotImplementedError('kind must be linear, '
                                  'parabolic, or hyperbolic...')
    # make axes unitless
    dpx = (np.abs(haxis[1] - haxis[0]) /
           np.abs(taxis[1] - taxis[0]))
    pxaxis = pxaxis * dpx
    haxisunitless = np.arange(nh)
    if centeredh:
        haxisunitless -= nh // 2
    dims = (npx, nt)
    dimsd = (nh, nt)

    if onthefly:
        if interp:
            fh = lambda x, y: _indices_2d_onthefly(f, haxisunitless, pxaxis,
                                               x, y, nt, interp=interp)[1:]
        else:
            fh = lambda x, y: _indices_2d_onthefly(f, haxisunitless, pxaxis,
                                                   x, y, nt, interp=interp)[1]
        r2op = Spread(dims, dimsd, fh=fh, engine=engine, dtype=dtype)
    else:
        table = np.full((npx, nt, nh), np.nan, dtype=np.float32)
        if interp:
            dtable = np.full((npx, nt, nh), np.nan)
        else:
            dtable = None

        for ipx, px in enumerate(pxaxis):
            for it in range(nt):
                xscan, tscan, dtscan = _indices_2d(f, haxisunitless, px,
                                                   it, nt,
                                                   interp=interp)
                table[ipx, it, xscan] = tscan
                if interp:
                    dtable[ipx, it, xscan] = dtscan
        r2op = Spread(dims, dimsd, table=table,
                      dtable=dtable, engine=engine,
                      dtype=dtype)
    return r2op
