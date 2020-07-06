"""
Kernel Polynomial Method
========================

The kernel polynomial method is an algorithm to obtain an approximation
for the spectral density of a Hermitian matrix. This algorithm combines
expansion in polynomials of Chebyshev [1], the stochastic trace [2] and a
kernel smothing techinique  in order to obtain the approximation for the 
spectral density

Applications
------------

- Hamiltonian matrices associated with quantum mechanics
- Laplacian matrix associated with a graph
- Magnetic Laplacian associated with directed graphs
- etc


References
----------

[1] Wang, L.W., 1994. Calculating the density of states and
optical-absorption spectra of large quantum systems by the plane-wave moments
method. Physical Review B, 49(15), p.10154.

[2] Hutchinson, M.F., 1990. A stochastic estimator of the trace of the
influence matrix for laplacian smoothing splines. Communications in
Statistics-Simulation and Computation, 19(2), pp.433-450.

=======
"""
import numpy as np
import tensorflow as tf
import cupy as cp

from emate.linalg import rescale_matrix, get_bounds
from emate.linalg.misc import rescale_cupy

from emate.utils.tfops.vector_factories import normal_complex

from emate.utils.tfops.kernels import jackson as tf_jackson
from emate.utils.cupyops.kernels import jackson as cupy_jackson

from emate.hermitian.tfops.kpm import get_moments, apply_kernel
from emate.hermitian.cupyops import kpm as cupyops


def rescale_kpm(ek, rho, scale_fact_a, scale_fact_b):

    ek = ek*scale_fact_a + scale_fact_b
    rho = rho/scale_fact_a
    return ek, rho

def pykpm(
    H,
    num_moments=10,
    num_vecs=10,
    extra_points=2,
    precision=32,
    lmin=None,
    lmax=None,
    epsilon=0.01,
    device='/gpu:0',
    swap_memory_while=False,
):
    """
    Kernel Polynomial Method using a Jackson's kernel. 

    Parameters
    ----------

        H: scipy sparse matrix
            The Hermitian matrix
        num_moments: int 
        num_vecs: int
            Number of random vectors in oder to aproximate the 
            trace
        extra_points: int
        precision: int 
            Single or double precision
        limin: float, optional
            The smallest eigenvalue
        lmax: float
            The highest eigenvalue
        epsilon: float
            Used to rescale the matrix eigenvalues into the interval
            [-1, 1]
    
    Returns
    -------

        ek: array of floats 
            An array with num_moments + extra_points approximated
            "eigenvalues"

        rho: array of floats
            An array containing the densities of each "eigenvalue"

    References
    ----------

        [1] Wang, L.W., 1994. Calculating the density of states and
        optical-absorption spectra of large quantum systems by the plane-wave moments
        method. Physical Review B, 49(15), p.10154.

        [2] Hutchinson, M.F., 1990. A stochastic estimator of the trace of the
        influence matrix for laplacian smoothing splines. Communications in
        Statistics-Simulation and Computation, 19(2), pp.433-450.


    """

    if (lmin is None) or (lmax is None):
        lmin, lmax = get_bounds(H)

    H, scale_fact_a, scale_fact_b = rescale_matrix(H, lmin, lmax,)

    coo = H.tocoo()
    if np.iscomplexobj(coo.data):
        if precision == 32:
            np_type = np.complex64
            tf_type = tf.complex64
        else:
            np_type = np.complex128
            tf_type = tf.complex128
    else:
        if precision == 32:
            np_type = np.float32
            tf_type = tf.float32
        else:
            np_type = np.float64
            tf_type = tf.float64

    sp_values = np.array(coo.data, dtype=np_type)
    sp_indices = np.mat([coo.row, coo.col], dtype=np.int64).transpose()

    feed_dict = {
        "sp_values:0": sp_values,
        "sp_indices:0": sp_indices,
    }

    dimension = H.shape[0]

    tf.compat.v1.reset_default_graph()
    with tf.device(device):
        sp_indices = tf.compat.v1.placeholder(dtype=tf.int64, name="sp_indices")
        sp_values = tf.compat.v1.placeholder(
            dtype=tf_type,
            name="sp_values"
        )
        H = tf.SparseTensor(
            sp_indices,
            sp_values,
            dense_shape=np.array(H.shape, dtype=np.int32)
        )

        alpha0 = normal_complex(
            shape=(dimension, num_vecs),
            precision=precision
        )
        moments = get_moments(H, num_vecs, num_moments, alpha0)
        kernel0 = tf_jackson(num_moments, precision=32)
        if precision == 64:
            moments = tf.cast(moments, tf.float32)
        ek, rho = apply_kernel(
            moments,
            kernel0,
            dimension,
            num_moments,
            num_vecs,
            extra_points
        )
        ek, rho = rescale_kpm(ek, rho, scale_fact_a, scale_fact_b)

    with tf.compat.v1.Session() as sess:
        ek, rho = sess.run([ek, rho], feed_dict)

    return ek, rho

def cupykpm(
    H,
    num_moments=10,
    num_vecs=10,
    extra_points=12,
    precision=32,
    lmin=None,
    lmax=None,
    epsilon=0.01
):

    dimension = H.shape[0]

    if (lmin is None) or (lmax is None):
        lmin, lmax = get_bounds(H)

    H  = cp.sparse.csr_matrix(
        (
            cp.array(H.data.astype("complex64")), 
            cp.array(H.indices),
            cp.array( H.indptr)
        ), 
        shape=H.shape, dtype="complex64"
    )

    H, scale_fact_a, scale_fact_b = rescale_cupy(H, lmin, lmax, epsilon)
    
    moments = cp.array([
        cupyops.get_moments(H, num_moments, dimension)
        for i in range(num_vecs)
    ])
    kernel0 = cupy_jackson(num_moments, precision=32)
 
    ek, rho = cupyops.apply_kernel(
        moments,
        kernel0,
        dimension,
        num_moments,
        num_vecs,
        extra_points
    )
    ek, rho = rescale_kpm(ek, rho, scale_fact_a, scale_fact_b)

    return rho, ek

tfkpm = pykpm
__all__ = ["pykpm", "cupykpm", "tfkpm"]
