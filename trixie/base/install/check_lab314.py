"""Compatibility checks by default; exact historical versions only with --snapshot."""
import argparse
import importlib
import importlib.metadata as md
import json
import os
from pathlib import Path
import platform
import re
import subprocess
import sys
import tempfile

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--contract', type=Path, default=Path(__file__).resolve().parents[1]/'config/lab314/packages.json')
parser.add_argument('--snapshot', action='store_true')
parser.add_argument('--prefix', type=Path, required=True)
parser.add_argument('--functional', action='store_true')
parser.add_argument('--require-spyder', action='store_true')
parser.add_argument('--require-opencv-target', action='store_true', help='verify the current Conda OpenCV and HDF5 versions')
mode = parser.add_mutually_exclusive_group()
mode.add_argument('--kernel-only', action='store_true', help='show native dependency and kernel startup diagnostics')
mode.add_argument('--reporting-only', action='store_true', help='run the headless PDF and HTML reporting checks')
args = parser.parse_args()
if args.snapshot and args.reporting_only:
    parser.error('--reporting-only requires the current reporting packages')
contract = json.loads(args.contract.read_text()) if args.snapshot else None
errors = []
if Path(sys.prefix).resolve() != args.prefix.resolve():
    errors.append(f'prefix {sys.prefix} != {args.prefix}')
if errors:sys.exit('\n'.join(errors))
sys.path.insert(0,str(Path(__file__).resolve().parent))
if args.reporting_only:
    from check_lab314_reporting import main as check_reporting
    check_reporting()
    sys.exit(0)
from lab314_kernel import (KernelProbeError, diagnose_dependencies, kernel_environment, large_arm64_pages,
                           probe_spyder_kernel, run_native_check)

if args.kernel_only:
    with tempfile.TemporaryDirectory(prefix='lab314-kernel-') as tmp:
        root = Path(tmp)
        env = kernel_environment(root)
        diagnose_dependencies(args.prefix, env)
        try:
            probe_spyder_kernel(root, env)
        except KernelProbeError as error:
            sys.exit(str(error))
    print('PASS Spyder kernel startup and scientific imports')
    sys.exit(0)

from lab314_policy import version_errors, policy, native_layout
native = native_layout(args.prefix)
versions={d.metadata['Name']:d.version for d in md.distributions()}
integrated_spyder = native and 'spyder' in versions
if native:
    for name in ('opencv-python','opencv-python-headless','spyder','spyder-kernels'):
        if name in versions and (md.distribution(name).read_text('INSTALLER') or '').strip() != 'conda':
            errors.append(f'{name} must be owned by Conda in the integrated environment')
if args.require_spyder and (not integrated_spyder or not os.access(args.prefix/'bin/spyder',os.X_OK)):
    errors.append('Conda Spyder and its launcher must be present in the scientific environment')
if args.require_opencv_target and (args.snapshot or not native):
    errors.append('The OpenCV target check requires the current Conda Scientific Python environment')
if args.snapshot:
    # Keep --contract support for exact snapshot diagnostics.
    if platform.python_version()!=contract['python']:errors.append('Snapshot Python version differs')
    for name,expected in contract['packages'].items():
        try:found=md.version(name)
        except md.PackageNotFoundError:found='MISSING'
        if found!=expected:errors.append(name+': snapshot version differs: '+found)
else:
    try:errors.extend(version_errors(versions,platform.python_version(),native=native))
    except ValueError as exc:errors.append(str(exc))
    for module in policy()['pip'].values():
        try:importlib.import_module(module)
        except Exception as exc:errors.append(module+': '+str(exc))
    if not errors:
        cv=importlib.import_module('cv2')
        gui=re.search(r'GUI:\s*(\S+)',cv.getBuildInformation())
        if not gui or gui[1].upper() in ('NONE','NO') or (native and gui[1].upper() != 'QT6'):
            errors.append('OpenCV must provide a graphical Linux backend')
        if args.require_opencv_target:
            target=policy()['native']
            hdf5_versions={'h5py':importlib.import_module('h5py').version.hdf5_version,
                           'netCDF4':importlib.import_module('netCDF4').__hdf5libversion__}
            if cv.__version__!=target['opencv']:
                errors.append(f"OpenCV version {cv.__version__}; expected {target['opencv']}")
            for module,found in hdf5_versions.items():
                if found!=target['hdf5']:
                    errors.append(f"{module} uses HDF5 {found}; expected {target['hdf5']}")
if '/usr/lib/python3/dist-packages' in sys.path:
    errors.append('Debian dist-packages leaks into lab314')
if not native:
    for font in ('DejaVuSans.ttf', 'DejaVuSans-Bold.ttf'):
        path = Path(sys.prefix)/'lib/python3.14/site-packages/cv2/qt/fonts'/font
        if not path.is_file():
            errors.append('missing Qt font '+str(path))
if errors:
    sys.exit('\n'.join(errors))
subprocess.run([sys.executable, '-B', '-m', 'pip', 'check'], check=True)
print('PASS', 'exact snapshot' if args.snapshot else 'compatible requirements', 'Python, prefix, isolation')
if not args.functional:
    sys.exit(0)
if not args.snapshot:
    subprocess.run([sys.executable, '-IB', str(Path(__file__).with_name('check_lab314_reporting.py'))], check=True)

# Small deterministic workloads. Temporary output follows the caller's TMPDIR.
with tempfile.TemporaryDirectory(prefix='lab314-check-') as tmp:
    root = Path(tmp)
    import numpy as np
    import scipy.linalg as la
    import pandas as pd
    import sympy
    import statsmodels.api as sm
    from sklearn.linear_model import LinearRegression
    from numba import njit
    from uncertainties import ufloat
    from pint import UnitRegistry
    from shapely.geometry import Point, LineString, Polygon, MultiPolygon
    import shapely
    import cv2
    import skimage.filters
    from PIL import Image
    import imageio.v3 as iio
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    import seaborn
    import xarray as xr
    import netCDF4
    import h5py
    import pyarrow as pa
    import pyarrow.parquet as pq
    if native and large_arm64_pages() and pa.default_memory_pool().backend_name == 'jemalloc':
        # The affected libarrow embeds its own allocator. Limit the fallback to
        # this verification process and keep the installed packages intact.
        pa.set_memory_pool(pa.system_memory_pool())
        print('PyArrow verification uses the system memory pool on ARM64 with large pages.')
    import tifffile
    import openpyxl
    import xlsxwriter
    import IPython, ipykernel, spyder_kernels, jupyterlab
    import tqdm, serial
    import rtree, gmpy2, formulaic, exifread, networkx
    import imageio_ffmpeg

    assert np.allclose(la.solve([[2., 0], [0, 4]], [4., 8.]), [2, 2])
    x = np.arange(6.).reshape(-1, 1)
    y = x[:, 0]*2+1
    assert np.allclose(LinearRegression().fit(x, y).predict(x), y)
    assert np.allclose(sm.OLS(y, sm.add_constant(x)).fit().params, [1, 2])
    assert njit(lambda a: a.sum())(np.arange(10)) == 45
    assert sympy.integrate(sympy.Symbol('x'), (sympy.Symbol('x'), 0, 2)) == 2
    assert (ufloat(2, .1)*2).nominal_value == 4
    assert (2*UnitRegistry().meter).to('cm').magnitude == 200
    p = Polygon([(0, 0), (2, 0), (2, 2), (0, 2)])
    q = Polygon([(1, 0), (3, 0), (3, 2), (1, 2)])
    assert p.area == 4 and p.intersection(q).area == 2 and p.union(q).area == 6
    assert Point(1, 1).within(p) and LineString([(0, 0), (2, 0)]).length == 2
    assert MultiPolygon([p, Polygon([(4, 0), (5, 0), (5, 1), (4, 1)])]).area == 5
    assert np.array_equal(shapely.area(np.array([p, q], dtype=object)), [4, 4])
    assert shapely.geos_version_string
    print('PASS Shapely Point/LineString/Polygon/MultiPolygon/intersection/union/area/NumPy GEOS',
          shapely.geos_version_string)
    im = np.zeros((48, 64, 3), np.uint8)
    im[:, :32] = (24, 100, 180)
    for suffix in ('png', 'jpg'):
        filename = str(root/('image.'+suffix))
        assert cv2.imwrite(filename, im)
        assert cv2.imread(filename).shape == im.shape
    assert cv2.getBuildInformation()  # Distribution identity is checked above.
    if args.snapshot:assert cv2.__version__==contract['opencv']
    assert skimage.filters.sobel(im[:, :, 0]).shape == (48, 64)
    assert cv2.contourArea(np.array(p.exterior.coords[:-1], dtype=np.float32)) == p.area
    for codec in ('FFV1', 'MJPG'):
        filename = str(root/(codec+'.avi'))
        writer = cv2.VideoWriter(filename, cv2.CAP_FFMPEG, cv2.VideoWriter_fourcc(*codec), 10, (64, 48))
        assert writer.isOpened()
        for _ in range(5):
            writer.write(im)
        writer.release()
        cap = cv2.VideoCapture(filename)
        for _ in range(5):
            ok, frame = cap.read()
            assert ok and frame.shape == im.shape
            if codec == 'FFV1':
                assert np.array_equal(frame, im)
        assert not cap.read()[0]
        cap.release()
    tifffile.imwrite(root/'im.tif', im)
    assert np.array_equal(iio.imread(root/'im.tif'), im)
    plt.plot([1, 2])
    plt.savefig(root/'plot.png')
    plt.close()
    assert Image.open(root/'plot.png').size[0] > 0
    with h5py.File(root/'a.h5', 'w') as h:
        h['im'] = im
    with h5py.File(root/'a.h5', 'r') as h:
        assert np.array_equal(h['im'][:], im)
    with netCDF4.Dataset(root/'direct.nc', 'w', format='NETCDF4') as nc:
        nc.createDimension('sample', 2)
        nc.createVariable('data', 'i4', ('sample',))[:] = [6, 7]
    with netCDF4.Dataset(root/'direct.nc', 'r') as nc:
        assert np.array_equal(nc.variables['data'][:], [6, 7])
    print('PASS HDF5 and NetCDF read/write', h5py.version.hdf5_version, netCDF4.__hdf5libversion__)
    frame = pd.DataFrame({'value': [1, 2]})
    pq.write_table(pa.Table.from_pandas(frame), root/'a.parquet')
    assert pq.read_table(root/'a.parquet').to_pandas().equals(frame)
    array = xr.DataArray([1., 2.], dims=['x'])
    array.to_netcdf(root/'a.nc')
    with xr.open_dataarray(root/'a.nc') as loaded:
        assert loaded.equals(array)
    book = xlsxwriter.Workbook(root/'a.xlsx')
    sheet = book.add_worksheet()
    sheet.write(0, 0, 42)
    book.close()
    assert openpyxl.load_workbook(root/'a.xlsx').active['A1'].value == 42
    assert gmpy2.is_prime(17)
    idx = rtree.index.Index()
    idx.insert(1, (0, 0, 1, 1))
    assert list(idx.intersection((0, 0, 1, 1))) == [1]
    assert formulaic.model_matrix('value', frame).shape[0] == 2
    assert networkx.shortest_path(networkx.path_graph(3), 0, 2) == [0, 1, 2]
    print('Scientific Python environment: PASS (calculations, Numba JIT, files, image/video and measurement data)')
    if native:
        env = kernel_environment(root)
        try:
            run_native_check([sys.executable,'-IB','-X','faulthandler','-c',
                'import cv2,numpy; cv2.namedWindow("probe"); cv2.imshow("probe",numpy.zeros((32,32),numpy.uint8)); '
                'cv2.waitKey(1); cv2.destroyAllWindows()'], env, 'OpenCV Qt6 HighGUI')
            print('PASS OpenCV Qt6 HighGUI offscreen window')
            if integrated_spyder:
                run_native_check([sys.executable,'-IB','-X','faulthandler','-c',
                    'import spyder; from qtpy import QtWebEngineWidgets,QtWidgets; '
                    'app=QtWidgets.QApplication([]); widget=QtWidgets.QWidget(); widget.show(); app.processEvents()'],
                    env, 'Spyder package and Qt bindings')
                print('Spyder package installation: PASS (imports)')
                probe_spyder_kernel(root, env)
                print('Jupyter kernel API test: PASS (NumPy, SciPy and OpenCV)')
        except KernelProbeError as error:
            sys.exit(str(error))
