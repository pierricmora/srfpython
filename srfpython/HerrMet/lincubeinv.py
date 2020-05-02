from __future__ import print_function
from builtins import  input
import sys, glob, os
import numpy as np
import matplotlib.pyplot as plt
from srfpython.HerrMet.nodefile import NodeFileString, NodeFile
from srfpython.HerrMet.theory import Theory
from srfpython.HerrMet.paramfile import load_paramfile
from srfpython.HerrMet.datacoders import makedatacoder, Datacoder_log
from srfpython.standalone.asciifile import AsciiFile
from srfpython.HerrMet.files import HERRMETEXTRACTPDFMODELFILE, HERRMETTARGETFILE, ROOTNAME
from srfpython.depthdisp.depthmodels import depthmodel_from_mod96, brocher2005, depthmodel_from_arrays, depthmodel1D, depthspace
from scipy.sparse import diags, csr_matrix, csc_matrix, save_npz as save_sparse_npz, load_npz as load_sparse_npz

"""
"""
rootdir = "../../tutorials/02_cube_inversion_example/inversion"
nodefile = "../../tutorials/02_cube_inversion_example/nodes.txt"
# resample the aposteri median at ztop defined below
#ztop = np.linspace(0., 3.0, 50)
ztop = depthspace(3, 12)
# povide the parameters used for the aposteriory pdf extraction
extract_mode = "best"
extract_limit = 1000
extract_llkmin = 0
extract_step = 1

horizontal_smoohting_distance = 50.0 * np.ones_like(ztop)  # one smoothing distance per layer
vertical_smoothing_distance = 1.

# node file
nf = NodeFile(nodefile, rootdir=rootdir)
nf.fill_extraction_files(
    extract_mode=extract_mode,
    extract_limit=extract_limit,
    extract_llkmin=extract_llkmin,
    extract_step=extract_step)

# =====================================
def haversine(loni, lati, lonj, latj, R=6371.):
    """
    Calculate the great circle distance between two points
    on the earth (specified in decimal degrees)
    source https://stackoverflow.com/questions/15736995/how-can-i-quickly-estimate-the-distance-between-two-latitude-longitude-points
    lone, late : coordinates of the first point, in degrees
    lons, lats : coordinates of the second point, in degrees
    :return distance in km

    consistent with Ll2DGAB
    """
    # convert decimal degrees to radians
    q = np.pi / 180.

    # haversine formula
    dlon = (loni - lonj)
    dlat = (lati - latj)
    a = np.sin(q * dlat / 2.) ** 2. + np.cos(q * latj) * np.cos(q * lati) * np.sin(q * dlon / 2.) ** 2.
    c = 2. * np.arcsin(np.sqrt(a))
    km = R * c
    return km

# ============================= CM
zmid = ztop + np.hstack((0.5 * (ztop[1:] - ztop[:-1]), 0.5 * np.median(ztop[1:] - ztop[:-1])))
CM_row_ind = np.array([], int)
CM_col_ind = np.array([], int)
CM_data = np.array([], float)
for n in range(len(nf)):
    # find the posterior unc at each depth on vs from the pointwise inversion

    vs84_n = depthmodel_from_mod96(nf.p84files[n]).vs
    vs16_n = depthmodel_from_mod96(nf.p16files[n]).vs
    vs84_n = depthmodel1D(ztop, vs84_n.interp(zmid))
    vs16_n = depthmodel1D(ztop, vs16_n.interp(zmid))
    vs_unc_n = 0.5 * (vs84_n.values - vs16_n.values)
    # vs_unc_n = np.ones_like(vs_unc_n)  ################### test

    # determine the vertical correlation coeff in cell n
    if vertical_smoothing_distance > 0:
        rhonn = np.exp(-np.abs(ztop - ztop[:, np.newaxis]) / vertical_smoothing_distance)
        covnn = vs_unc_n[:, np.newaxis] * vs_unc_n * rhonn

        row_ind, col_ind = np.meshgrid(range(len(ztop)), range(len(ztop)))
        CM_row_ind = np.hstack((CM_row_ind, n * len(ztop) + row_ind.flat[:]))
        CM_col_ind = np.hstack((CM_col_ind, n * len(ztop) + col_ind.flat[:]))
        CM_data = np.hstack((CM_data, covnn.flat[:]))
    else:
        covnn_diags = vs_unc_n ** 2.0
        CM_row_ind = np.hstack((CM_row_ind, n * len(ztop) + np.arange(len(ztop))))
        CM_col_ind = np.hstack((CM_col_ind, n * len(ztop) + np.arange(len(ztop))))
        CM_data = np.hstack((CM_data, covnn_diags.flat[:]))

    for m in range(n + 1, len(nf)):
        lonn = nf.lons[n]
        latn = nf.lats[n]
        lonm = nf.lons[m]
        latm = nf.lats[m]

        vs84_m = depthmodel_from_mod96(nf.p84files[m]).vs
        vs16_m = depthmodel_from_mod96(nf.p16files[m]).vs
        vs84_m = depthmodel1D(ztop, vs84_m.interp(zmid))
        vs16_m = depthmodel1D(ztop, vs16_m.interp(zmid))
        vs_unc_m = 0.5 * (vs84_m.values - vs16_m.values)
        # vs_unc_m = np.ones_like(vs_unc_m)  ################### test

        dnm = haversine(lonn, latn, lonm, latm)
        rhonm_diags = np.exp(-dnm / horizontal_smoohting_distance)
        covnm_diags = vs_unc_n * vs_unc_m * rhonm_diags

        CM_row_ind = np.hstack((CM_row_ind, n * len(ztop) + np.arange(len(ztop))))
        CM_col_ind = np.hstack((CM_col_ind, m * len(ztop) + np.arange(len(ztop))))
        CM_data = np.hstack((CM_data, covnm_diags.flat[:]))

        CM_row_ind = np.hstack((CM_row_ind, m * len(ztop) + np.arange(len(ztop))))
        CM_col_ind = np.hstack((CM_col_ind, n * len(ztop) + np.arange(len(ztop))))
        CM_data = np.hstack((CM_data, covnm_diags.flat[:]))

CM = csc_matrix((CM_data, (CM_row_ind, CM_col_ind)), shape=(len(nf) * len(ztop), len(nf) * len(ztop)))
if False:
    assert input('sure ({})?)'.format(CM.shape)) == "y"
    CM = CM.toarray()
    assert (CM.T == CM).all()
    plt.figure()
    plt.imshow(CM)
    plt.show()
save_sparse_npz('CM.npz', CM)

# from scipy.sparse.linalg import inv as sparseinv
# CMinv = sparseinv(CM)
# CMinv = CMinv.toarray()
# plt.figure()
# plt.imshow(CMinv == 0.)
# plt.show()

# ============================= G, CDinv, Dobs, Dcalc
G_current_row = 0
G_current_col = 0
G_row_ind = np.array([], int)
G_col_ind = np.array([], int)
G_fd_data = np.array([], float)
CDinv_diag_data = np.array([], float)
Dobs = np.array([], float)
Dcalc = np.array([], float)
for nnode, (node, lon, lat, targetfile, paramfile, medianfile, p16file, p84file) in enumerate(nf):

    print(node, lon, lat)
    print("    ", targetfile)
    print("    ", paramfile)
    print("    ", medianfile)
    print("    ", p16file)
    print("    ", p84file)

    # load the extracted file
    dm = depthmodel_from_mod96(medianfile)

    # resample to ztop
    vs = dm.vs.interp(zmid)
    # plt.figure()
    # dm.vs.show(plt.gca())
    # vsi = depthmodel_from_arrays(ztop, vs+1., vs, vs/2.)
    # vsi.show(plt.gca())
    # plt.show()

    # ============================= G
    # write a parameter file for the optimizer
    parameter_string = """
    #met NLAYER = {}
    #met TYPE = 'mZVSVPvsRHvp'
    #met VPvs = 'lambda VS: 0.9409 + 2.0947 * VS - 0.8206 * VS ** 2.0 + 0.2683 * VS ** 3.0 - 0.0251 * VS ** 4.0'
    #met RHvp = 'lambda VP: 1.6612 * VP - 0.4721 * VP ** 2.0 + 0.0671 * VP ** 3.0 - 0.0043 * VP ** 4.0 + 0.000106 * VP ** 5.0'
    #fld KEY     VINF          VSUP
    #unt []      []            []
    #fmt %s      %f            %f
    """.format(len(ztop)).replace('    #', '#')

    for i in range(1, len(ztop)):
        # force VINF=VSUP => means lock the depth of the interfaces in the theory operator
        parameter_string += "-Z{} {} {}\n".format(i, -ztop[i], -ztop[i])  # add locked depth interfaces

    for i in range(len(ztop)):
        # SET VINF < VS extracted from pointwise inv < VSUP
        # such as parameterizer.MMEAN corresponds to the extracted vs
        parameter_string += "VS{} {} {}\n".format(i, vs[i]-0.01, vs[i]+0.01)

    # initiate the parameterizer and datacoder
    parameterizer, _ = load_paramfile(parameter_string, verbose=False)
    datacoder = makedatacoder(targetfile, which=Datacoder_log)

    # initiate the theory operator (g)
    theory = Theory(parameterizer=parameterizer, datacoder=datacoder)

    # compute Frechet derivatives near parameterizer.MMEAN
    m = parameterizer.MMEAN
    gm = theory(m)
    Dcalc = np.concatenate((Dcalc, gm))

    fd = theory.frechet_derivatives(m=m, gm=gm)
    fd_col_ind, fd_row_ind = np.meshgrid(range(fd.shape[1]), range(fd.shape[0]))

    # qc
    if 0:
        import matplotlib.pyplot as plt
        plt.gcf().clf()
        plt.ion()
        plt.imshow(fd)
        plt.show()
        input('pause')

    # store indices and values to fill the sparse matrix G
    G_row_ind = np.concatenate((G_row_ind, G_current_row + fd_row_ind.flat[:]))
    G_col_ind = np.concatenate((G_col_ind, G_current_col + fd_col_ind.flat[:]))
    G_fd_data = np.concatenate((G_fd_data, fd.flat[:]))

    # increment position in the global G matrix
    G_current_row = G_row_ind[-1] + 1
    G_current_col = G_col_ind[-1] + 1

    # ============================= CDinv and Dobs
    dobs_current, CDinv_diag_current = datacoder.target()
    CDinv_diag_data = np.concatenate((CDinv_diag_data, CDinv_diag_current))
    Dobs = np.concatenate((Dobs, dobs_current))


# ============================= save matrixes to disk
G = csr_matrix((G_fd_data, (G_row_ind, G_col_ind)), shape=(G_current_row, G_current_col))
CD = diags(CDinv_diag_data ** -1.0, offsets=0, format="csr", dtype=float)
CDinv = diags(CDinv_diag_data, offsets=0, format="csr", dtype=float)

# np.save('CDinv_diag.npy', CDinv_diag, allow_pickle=False)
save_sparse_npz('G.npz', G)
save_sparse_npz('CD.npz', CDinv)
save_sparse_npz('CDinv.npz', CDinv)
np.save('Dobs.npy', Dobs, allow_pickle=False)
np.save('Dcalc.npy', Dcalc, allow_pickle=False)


# =============================
del G
del CDinv
G = load_sparse_npz('G.npz')
#CDinv_diag = np.load('CDinv_diag.npy')
CDinv = load_sparse_npz('CDinv.npz')
Dobs = np.load('Dobs.npy')
Dcalc = np.load('Dcalc.npy')


if False:
    input('sure?')
    G = G.toarray()
    import matplotlib.pyplot as plt
    plt.figure()
    plt.imshow(G) #.toarray())
    plt.show()
