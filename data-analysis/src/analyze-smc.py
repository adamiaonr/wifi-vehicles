# analyze-trace.py : code to analyze custom wifi trace collections
# Copyright (C) 2018  adamiaonr@cmu.edu

# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.

# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.

import os
import argparse
import sys
import sqlalchemy

# custom imports
# - analysis.smc
import analysis.smc.utils
import analysis.smc.database
import analysis.smc.sessions.extract
# - plot.smc
import plot.smc.roads
import plot.smc.sessions
# - hdfs utils
import utils.hdfs
# - mapping utils
import utils.mapping.openstreetmap
import utils.mapping.utils

# gps coords for a 'central' pin on porto, portugal
LAT  = 41.163158
LON = -8.6127137
# north, south, west, east limits of map, in terms of geo coordinates
LATN = LAT + 0.03
LATS = LAT - 0.03
LONE = LON + 0.06
LONW = LON - 0.06

if __name__ == "__main__":

    # use an ArgumentParser for a nice CLI
    parser = argparse.ArgumentParser()

    # options (self-explanatory)
    parser.add_argument(
        "--input-dir", 
         help = """dir w/ smc data""")

    parser.add_argument(
        "--output-dir", 
         help = """dir to save processed data""")

    parser.add_argument(
        "--graph-dir", 
         help = """dir to save graphs""")

    parser.add_argument(
        "--populate", 
         help = """populates sql tables w/ data""")

    parser.add_argument(
        "--db-name", 
         help = """name of db to use""")    

    parser.add_argument(
        "--list-dbs", 
         help = """lists dbs in .hdfs database""",
         action = 'store_true')

    parser.add_argument(
        "--remove-dbs", 
         help = """list of .hdfs keys to remove, separated by ','.
                e.g. --remove-dbs '/db1, /db2'""")

    parser.add_argument(
        "--analyze-roads", 
         help = """list of road names to analyze, separated by ','. 
                e.g.: --analyze-roads 'Rua da Boavista,Avenida da Boavista'""") 

    parser.add_argument(
        "--analyze-sessions", 
         help = """high-level smc dataset analysis""",
                action = 'store_true') 

    args = parser.parse_args()

    if not args.input_dir:
        sys.stderr.write("""%s: [ERROR] must provide a dir w/ input files\n""" % sys.argv[0]) 
        parser.print_help()
        sys.exit(1)

    if not args.output_dir:
        sys.stderr.write("""%s: [ERROR] must provide an output dir\n""" % sys.argv[0]) 
        parser.print_help()
        sys.exit(1)

    if not args.graph_dir:
        sys.stderr.write("""%s: [ERROR] must provide a graph dir\n""" % sys.argv[0]) 
        parser.print_help()
        sys.exit(1)

    if not args.db_name:
        sys.stderr.write("""%s: [ERROR] must a db name\n""" % sys.argv[0]) 
        parser.print_help()
        sys.exit(1)        

    if args.list_dbs:
        database = utils.hdfs.get_db(args.input_dir, ('%s.hdf5' % (args.db_name)))
        database_keys = utils.hdfs.get_db_keys(args.input_dir, ('%s.hdf5' % (args.db_name)))
        sys.stderr.write("""%s: [INFO] keys in .hdfs database:\n""" % (sys.argv[0]))
        for key in database_keys:
            print('\t%s' % (key))

    if args.remove_dbs:
        utils.hdfs.remove_dbs(args.input_dir, args.remove_dbs.split(','))

    db_str = ('mysql+mysqlconnector://root:xpto12x1@localhost/%s' % (args.db_name))
    db_eng = sqlalchemy.create_engine(db_str)

    if args.populate:

        # fill roads & cells tables
        bbox = [LONW, LATS, LONE, LATN]
        osm_tags = ['highway=motorway', 'highway=trunk', 'highway=primary', 'highway=secondary', 'highway=tertiary', 'highway=residential']

        if args.populate == 'sessions':

            # create tables:
            #   - roads
            utils.mapping.openstreetmap.create_roads_table(args.output_dir, bbox, osm_tags, db_eng = db_eng)
            #   - roads cells 'link' table
            utils.mapping.openstreetmap.create_roads_cells_table(args.output_dir, bbox, osm_tags, db_eng = db_eng)
            #   - operator
            analysis.smc.database.create_operator_table(db_eng = db_eng)
            #   - session data
            analysis.smc.database.insert_sessions(args.input_dir, db_eng = db_eng)

        if args.populate == 'road-stats':

            analysis.smc.database.create_road_stats_table(db_eng = db_eng, db_name = args.db_name)

            queries = {
                'road-stats' : {
                    'query' : """SELECT 
                        rs.road_id, name, length,
                        ap_cnt, ess_cnt, op_cnt, rss_cnt_avg, rss_cnt_std,
                        rss_1, rss_2, rss_3,
                        num_cells
                    FROM road_stats rs
                    INNER JOIN roads r
                    ON rs.road_id = r.id
                    INNER JOIN road_rss_stats rrs
                    ON r.id = rrs.road_id""",
                    'filename' :  os.path.join(args.output_dir, 'road-stats.csv')
                },

                'road-sessions' : {
                    'query' : """SELECT *
                    FROM road_session_stats""",
                    'filename' :  os.path.join(args.output_dir, 'road-sessions.csv')
                },
            }
            
            analysis.smc.database.to_csv(queries, db_eng = db_eng, db_name = args.db_name)

    if args.analyze_roads:

        roads = args.analyze_roads.split(',')

        # for road in roads:
        # #     analysis.smc.roads.extract.coverage(name = road, input_dir = args.input_dir, db_eng = db_eng)
        #     analysis.smc.roads.utils.print_info(name = road, input_dir = args.input_dir, db_eng = db_eng)

        # plot.smc.roads.handoff(args.input_dir, args.graph_dir, strategy = 'best-rss')
        # plot.smc.roads.coverage_blocks(args.input_dir, args.graph_dir)
        # plot.smc.roads.coverage(args.input_dir, args.graph_dir, strategy = 'best-rss')
        plot.smc.roads.coverage(args.input_dir, args.graph_dir, strategy = 'best-rss', db_name = args.db_name)
        # plot.smc.roads.signal_quality(args.input_dir, args.graph_dir)
        # plot.smc.roads.map(args.input_dir, args.graph_dir)
#        plot.smc.roads.rss(args.input_dir, args.graph_dir, 
#            road_id = 834,
#            strategy = 'raw', 
#            restriction = {'open' : 'any', 'operator' : 'any', 'label' : 'any', 'threshold' : -80.0})

    if args.analyze_sessions:

        # analysis.smc.sessions.extract.device_scans(args.input_dir, db_eng = db_eng, db_name = args.db_name)
        # plot.smc.sessions.device_scans(args.input_dir, args.graph_dir)

        # plot_contact(database, args.output_dir)
        # plot_bands(database, args.output_dir)

        # analysis.smc.sessions.extract_contact(args.input_dir)
        # analysis.smc.sessions.extract_signal_quality(args.input_dir)
        # analysis.smc.sessions.extract_esses(args.input_dir, db_eng = db_eng)
        # analysis.smc.sessions.extract_session_nr(args.input_dir)
        # analysis.smc.sessions.extract_channels(args.input_dir)
        # analysis.smc.sessions.extract_auth(args.input_dir)
        # analysis.smc.sessions.extract_operators(args.input_dir)

        plot.smc.sessions.signal_quality(args.input_dir, args.graph_dir, db_name = args.db_name)
        plot.smc.sessions.esses(args.input_dir, args.graph_dir, draw_map = False)
        # plot.smc.sessions.channels(args.input_dir, args.graph_dir)
        # plot.smc.sessions.auth(args.input_dir, args.graph_dir)
        # plot.smc.sessions.operators(args.input_dir, args.graph_dir)

    sys.exit(0)