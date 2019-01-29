import numpy as np
import giapy
from scipy.interpolate import interp1d

import giapy.apl_tools.t_files
import giapy.data_tools.gpsdata
import giapy.data_tools.tiltdata

# ESL definition
esldat = np.loadtxt(giapy.MODPATH+'/data/obs/Meltwater_last_glacial_cycle_p00mmpy.txt').T
esl = interp1d(esldat[0]/1000, esldat[1])

def read_ice_assignments(fname):
    with open(fname, 'r') as f:
        nglaciers = int(f.readline().split(',')[0])
        alterdict = {}
        alternum = {}

        for i in range(14):
            l = f.readline().split(',')
            num = int(l[0])
            name = l[4]
            toplonlat = []
            for item in f.readline().split(','):
                try:
                    toplonlat.append(float(item))
                except:
                    break
            botlonlat = []
            for item in f.readline().split(','):
                try:
                    botlonlat.append(float(item))
                except:
                    break

            lonlat = np.hstack([np.vstack([toplonlat[::2], toplonlat[1::2]]),
                                np.vstack([botlonlat[::2], botlonlat[1::2]])[:,::-1]])

            alterdict[num] = lonlat.T 
            alternum[name] = num
    return alterdict, alternum

def load_ice_modifications(propfname, glacfname, ice, grid):

    #larry_output_order = ['cor', 'laur', 'naf', 'inu', 'grn', 'ice', 'fen',
    #'want', 'eant', 'bar', 'sval', 'fjl', 'nz', 'eng']

    alterdict, alternum = read_ice_assignments(glacfname)

    with open(propfname, 'r') as f:
        text = f.readlines()

    #times = [float(w.strip())/1000 for w in text[1].split(',')[1:]]

    #newtimes = [10.5, 9.5, 8.5, 7.2, 6., 5.25, 5., 4.75]

    #sortinds = np.argsort(np.r_[times, newtimes])

    props = {}
    for line in text[5:]:
        if ',' in line:
            data = [entry.strip() for entry in line.split(',')]
        elif '\t' in line:
            data = [entry.strip() for entry in line.split('\t')]
            
        prop = [1+float(num) for num in data[1:]]
        name = data[0]
        num = alternum[name]
        #newprop = np.interp(newtimes, times, prop)
        #prop = (np.r_[prop, newprop])[sortinds][::-1]
        # append 0
        prop = np.r_[prop[::-1], [1]]


        props[num] = prop

    ice.createAlterationAreas(grid, props.values(), alterdict.keys(), alterdict)

    return ice.applyAlteration()

def read_dupuit_ice(fname):
    """Read a Dupuit Ice model csv, who's structure is:
    Lon   Lat   t0   t1   t2   ...
    """
    ice = np.loadtxt(fname, delimiter=',', skiprows=1)
    ice = ice.reshape((288,288,-1)).transpose((2,0,1))

    f = open(fname, 'r')
    l = f.readline()
    col = l.split(',')

    ts = np.array(map(float, col[2:]))/1000. 

    metadata = {'fnames': '',
                'Lon': ice[0],
                'Lat': ice[1],
                'nlat': 288,
                'stageOrder':np.arange(len(ts)),
                'path':'',
                'shape':(288,288),
                'times':ts,
                'areaProps':None}

    ice = giapy.icehistory.PersistentIceHistory(ice[2:], metadata=metadata)
    ice.appendLoadCycle(esl)
    ice.times = ice.times

    # Add -100 and +100 years.
    ice.times = np.union1d(ice.times, [-.1,.1])[::-1]
    ice.stageOrder = np.r_[ice.stageOrder, 0, 0]

    return ice

def create_load_cycles(ice, n):
    """Append load cycles to the ice model.

    Accomplished by repeating the stage order and poisitive times.
    """

    # Taking only positive times avoids collision between cycles.
    addtimes = ice.times[ice.times>0]
    addstages = ice.stageOrder[ice.times>0]

    # Copy the arrays before changing them
    newtimes = ice.times.copy()
    newstages = ice.stageOrder.copy()

    for i in range(n-1):
        # Append the times (shifted by the max time) and stage numbers.
        newtimes = np.r_[addtimes+newtimes.max(), newtimes]
        newstages = np.r_[addstages, newstages]

    # Replace times and stage numbers and return.
    ice.times = newtimes
    ice.stageOrder = newstages

    return ice

if __name__ == '__main__':
    import sys, subprocess,os
    import argparse

    parser = argparse.ArgumentParser(description='Compute and output GIA for '
                                                  'APL GlacialRebound program')
    parser.add_argument('casename', type=str, help='Name of case to run (for output)')
    parser.add_argument('alterfile', type=str, help='''Path to ice alteration (or
                                                    dupuit model if --dupuit set)''')
    parser.add_argument('glacfile', type=str, help='''Path to glacier definitions.''')
    parser.add_argument('tnochange', type=float, help='''Time after which no ice
                                                        change.''')
    parser.add_argument('--earth', type=str, default=None, help='''Path to earth model''')
    parser.add_argument('--tfiles', default=False,
                            action='store_const', const=True,
                            dest='tfiles')
    parser.add_argument('--ncyc', default=1, type=int, help='''Number of glacial cycles.''')
    parser.add_argument('--topoit', default=1, type=int, help='''Number of iterations for 
                            initial topography (matches end topogrphy to
                            present day.''')
    parser.add_argument('--bathtub', default=False, action='store_const',
                        const=True, help='''Use to ignore marine-based ice and
                                            coast slopes.''')
    parser.add_argument('--ice6g', default=False, action='store_const',
                        const=True, help='Use ice6g as base ice model.')
    parser.add_argument('--dupuit', default=False, action='store_const',
                        const=True, help='Load Dupuit ice model from file')

    comargs = parser.parse_args()

    casename, alterfile = comargs.casename, comargs.alterfile
    glacfile, tnochange = comargs.glacfile, comargs.tnochange 

    earth = comargs.earth
    tfileflag = comargs.tfiles
    ncyc = comargs.ncyc
    topoit = comargs.topoit
    bathtub=comargs.bathtub

    if comargs.ice6g:
        icename = 'ice6g_pers_square'
        toponame = 'sstopo_ice6g'
    else:
        icename = 'aa2_base_pers_288'
        toponame = 'sstopo288'

    configdict = {'ice': icename,
                  'earth': '75km0p04Asth_4e23Lith',
                  'topo': toponame}

    sim = giapy.giasim.configure_giasim(configdict)
    topo0 = sim.topo.copy()
    dtopo = np.zeros_like(topo0)

    if earth is not None:
        print('Loading earth model: {}'.format(earth))
        earth = np.load(open(earth, 'r'))
        sim.earth = earth
        assert earth.nmax >= 288, 'earth must be at least 288 resolution'
    
    print('Inputs loaded\r')

    if comargs.dupuit:
       sim.ice = read_dupuit_ice(alterfile)

    sim.ice.stageOrder = np.array(sim.ice.stageOrder)
    sim.ice.stageOrder[sim.ice.times <= tnochange] = sim.ice.stageOrder[-1]

    if not comargs.ice6g and not comargs.dupuit:
        sim.ice = load_ice_modifications(alterfile, glacfile, sim.ice, sim.grid)

    sim.ice = create_load_cycles(sim.ice, ncyc)

    # Get rid of noise in Aleksey's model. The noise is scattered around North
    # America and Antarctica with some points exceeding 2 meters at LGM, so 5 
    # meters was chosen as the cutoff.
    sim.ice.stageArray[sim.ice.stageArray < 5] *= 0 

    print('Ice load modified\r')

    for i in range(topoit):
        result = sim.performConvolution(out_times=sim.ice.times,
                                        bathtub=bathtub)
        dtopo = result.sstopo.nearest_to(0) - topo0
        sim.topo -= dtopo
    
 
    print('Result computed, writing out case files\r')

    emergedatafile = giapy.MODPATH+'/data/obs/Emergence_Data_seqnr_2018.txt'
    emergedata = giapy.data_tools.emergedata.importEmergeDataFromFile(emergedatafile)
    rsldata = giapy.load(giapy.MODPATH+'/data/obs/psmsl_download_02082017.p')
    gpsdata = np.load(giapy.MODPATH+'/data/obs/gps_obs.p')
    tiltdata = giapy.data_tools.tiltdata.TiltData()

    giapy.apl_tools.t_files.write_case_files(casename, result,
                                                tfileflag=tfileflag)
    print('Result computed, writing out data files\r')
    giapy.apl_tools.t_files.write_data_files(casename, result,
                        emergedata=emergedata, rsldata=rsldata,
                        gpsdata=gpsdata, tiltdata=tiltdata)

    print os.path.abspath(os.path.curdir)
    command = 'cp {0} ./{1} && cp {2} ./{1}'.format(alterfile,
                                                        casename,
                                                        glacfile)
    print command
    subprocess.call(command, shell=True)
