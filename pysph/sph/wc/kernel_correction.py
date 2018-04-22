from pysph.sph.equation import Equation
from pysph.sph.wc.density_correction import gj_solve


class KernelCorrection(Equation):
    r"""**Kernel Correction**

    .. math::
            \mathbf{f}_{a} = \frac{\sum_{b}\frac{m_{b}}{\rho_{b}}
            \mathbf{f}_{b}W_{ab}}{\sum_{b}\frac{m_{b}}{\rho_{b}}W_{ab}}
    References
    ----------
    .. [Bonet and Lok, 1999] Bonet, J. and Lok T.-S.L. (1999)
        Variational and Momentum Preservation Aspects of Smoothed
        Particle Hydrodynamic Formulations.

    """

    def initialize(self, d_idx, d_cwij):
        d_cwij[d_idx] = 0.0

    def loop(self, d_idx, s_idx, d_cwij, s_m, s_rho, WIJ):
        d_cwij[d_idx] += s_m[s_idx] * WIJ / s_rho[s_idx]


class GradientCorrectionPreStep(Equation):

    def __init__(self, dest, sources, dim=2):
        self.dim = dim
        super(GradientCorrectionPreStep, self).__init__(dest, sources)

    def initialize(self, d_idx, d_m_mat):
        i = declare('int')
        for i in range(9):
            d_m_mat[9 * d_idx + i] = 0.0

    def loop_all(self, d_idx, d_m_mat, s_m, s_rho, d_x, d_y, d_z, d_h, s_x,
                 s_y, s_z, s_h, KERNEL, NBRS, N_NBRS):
        x = d_x[d_idx]
        y = d_y[d_idx]
        z = d_z[d_idx]
        h = d_h[d_idx]
        i, j, s_idx, n = declare('int', 4)
        xij = declare('matrix(3)')
        dwij = declare('matrix(3)')
        n = self.dim
        for k in range(N_NBRS):
            s_idx = NBRS[k]
            xij[0] = x - s_x[s_idx]
            xij[1] = y - s_y[s_idx]
            xij[2] = z - s_z[s_idx]
            hij = (h + s_h[s_idx]) * 0.5
            r = sqrt(xij[0] * xij[0] + xij[1] * xij[1] + xij[2] * xij[2])
            KERNEL.gradient(xij, r, hij, dwij)
            dw = sqrt(dwij[0] * dwij[0] + dwij[1] * dwij[1]
                      + dwij[2] * dwij[2])
            V = s_m[s_idx] / s_rho[s_idx]
            if r >= 1.0e-12:
                for i in range(n):
                    xi = xij[i]
                    for j in range(n):
                        xj = xij[j]
                        d_m_mat[9 * d_idx + 3 * i + j] += dw * V * xi * xj / r


class GradientCorrection(Equation):
    r"""**Kernel Gradient Correction**

    .. math::
            \nabla \tilde{W}_{ab} = L_{a}\nabla W_{ab}

    .. math::
            L_{a} = \left(\sum \frac{m_{b}}{\rho_{b}}\nabla W_{ab}
            \mathbf{\times}x_{ab} \right)^{-1}
    References
    ----------
    .. [Bonet and Lok, 1999] Bonet, J. and Lok T.-S.L. (1999)
        Variational and Momentum Preservation Aspects of Smoothed
        Particle Hydrodynamic Formulations.
    """

    def _get_helpers_(self):
        return [gj_solve]

    def __init__(self, dest, sources, dim=2, tol=0.5):
        self.dim = dim
        self.tol = tol
        super(GradientCorrection, self).__init__(dest, sources)

    def loop(self, d_idx, d_m_mat, DWIJ, HIJ):
        i, j, n = declare('int', 3)
        n = self.dim
        temp = declare('matrix(9)')
        res = declare('matrix(3)')
        eps = 1.0e-04 * HIJ
        for i in range(n):
            for j in range(n):
                temp[n * i + j] = d_m_mat[9 * d_idx + 3 * i + j]
        gj_solve(temp, DWIJ, n, res)
        change = 0.0
        for i in range(n):
            change += abs(DWIJ[i] - res[i]) / (abs(DWIJ[i]) + eps)
        if change <= self.tol:
            for i in range(n):
                DWIJ[i] = res[i]


class MixedKernelCorrectionPreStep(Equation):
    r"""**Kernel Correction**

    .. math::
            \tilde{W}_{ab} = \frac{W_{ab}}{\sum_{b} V_{b}W_{ab}}

    .. math::
            \nabla \tilde{W}_{ab} = L_{a}\nabla \bar{W}_{ab}

    where,

    .. math::
            L_{a} = \left(\sum_{b} V_{b}}\nabla \bar{W}_{ab}
            \mathbf{\times}x_{ab} \right)^{-1}

    .. math::
            \nabla \bar{W}_{ab} = \frac{\nabla W_{ab} - \gamma}
            {\sum_{b} V_{b}W_{ab}}

    ..math::
            \gamma = \frac{\sum_{b} V_{b}\nabla W_{ab}}
            {\sum_{b} V_{b}W_{ab}}
    References
    ----------
    .. [Bonet and Lok, 1999] Bonet, J. and Lok T.-S.L. (1999)
        Variational and Momentum Preservation Aspects of Smoothed
        Particle Hydrodynamic Formulations.

    """

    def __init__(self, dest, sources, dim=2):
        self.dim = dim
        super(MixedKernelCorrectionPreStep, self).__init__(dest, sources)

    def initialize(self, d_idx, d_m_mat):
        i = declare('int')
        for i in range(9):
            d_m_mat[9 * d_idx + i] = 0.0

    def loop_all(self, d_idx, d_x, d_y, d_z, d_h, s_x, s_y, s_z, s_h, KERNEL,
                 N_NBRS, NBRS, d_m_mat, s_m, s_rho, d_cwij):
        x = d_x[d_idx]
        y = d_y[d_idx]
        z = d_z[d_idx]
        h = d_h[d_idx]
        i, j, n, k, s_idx = declare('int', 5)
        n = self.dim
        xij = declare('matrix(3)')
        dwij = declare('matrix(3)')
        dwij1 = declare('matrix(3)')
        numerator = declare('matrix(3)')

        for i in range(3):
            numerator[i] = 0.0
            dwij1[i] = 0.0
        den = 0.0

        for k in range(N_NBRS):
            s_idx = NBRS[k]
            xij[0] = x - s_x[s_idx]
            xij[1] = y - s_y[s_idx]
            xij[2] = z - s_z[s_idx]
            V = s_m[s_idx] / s_rho[s_idx]
            rij = sqrt(xij[0] * xij[0] + xij[1] * xij[1] + xij[2] * xij[2])
            hij = (h + s_h[s_idx]) * 0.5
            KERNEL.gradient(xij, rij, hij, dwij)
            wij = KERNEL.kernel(xij, rij, hij)
            den += V * wij
            for i in range(n):
                numerator[i] += V * dwij[i]
        d_cwij[d_idx] = den

        for k in range(N_NBRS):
            s_idx = NBRS[k]
            xij[0] = x - s_x[s_idx]
            xij[1] = y - s_y[s_idx]
            xij[2] = z - s_z[s_idx]
            hij = (h + s_h[s_idx]) * 0.5
            r = sqrt(xij[0] * xij[0] + xij[1] * xij[1] + xij[2] * xij[2])
            KERNEL.gradient(xij, r, hij, dwij)
            for i in range(n):
                dwij1[i] = (dwij[i] - numerator[i] / den) / den
            dw = sqrt(dwij1[0] * dwij1[0] + dwij1[1]
                      * dwij1[1] + dwij1[2] * dwij1[2])
            V = s_m[s_idx] / s_rho[s_idx]
            if r >= 1.0e-12:
                for i in range(n):
                    xi = xij[i]
                    for j in range(n):
                        xj = xij[j]
                        d_m_mat[9 * d_idx + 3 * i + j] += dw * V * xi * xj / r
