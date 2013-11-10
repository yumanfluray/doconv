#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""doconv

Usage:
  doconv [options] <file> <input_format> <output_format>
  doconv (-h | --help)

Options:
  -o --out-file=<of>  File generated as output of the conversion.
  -v --verbose        Show additional information.
  -h --help           Show this screen.
  --version           Show version.

"""

from docopt import docopt
from stevedore import extension, driver
from networkx import nx
import sys
import os
from os import path
import shutil
import logging
# doconv imports
import log
from util import append_random_suffix, get_version

global logger
logger = log.setup_custom_logger('root')


def choose_best_conversion_path(conversion_graph, input_format, output_format):
    try:
        graph_path = nx.shortest_path(
            conversion_graph, input_format, output_format)
    except nx.NetworkXNoPath:
        raise Exception("""
        No combination of plugins available in doconv can convert from
        {0} to {1}""".format(input_format, output_format))
    return graph_path if conversion_graph is not None else None


def create_graph():
    """Composes the graphs of the different plugins into a single graph.
    """
    # load plugins
    mgr = extension.ExtensionManager(
        namespace='doconv.converter',
        invoke_on_load=True,
        propagate_map_exceptions=True,
    )

    # check that all plugin dependencies are installed
    mgr.map_method("check_dependencies")
    # create conversion graph based on found plugins
    plugin_graphs = mgr.map_method("get_supported_conversions_graph")
    logger.debug("Loaded plugins: {0}".format(mgr.names()))

    G = nx.DiGraph()
    for graph in plugin_graphs:
        G = nx.compose(G, graph)
    return G


def get_plugin_chain(graph, graph_path):
    """Following the graph_path creates an ordered list of the plugins to be
    called and the input and output format to be used with each plugin.
    """
    plugin_chain = []
    for node_pos in range(len(graph_path) - 1):
        input_format = graph_path[node_pos]
        output_format = graph_path[node_pos + 1]
        plugin = graph[input_format][output_format]['plugin']
        plugin_chain.extend([tuple([plugin, input_format, output_format])])
    return plugin_chain


def get_converter(name):
    """Returns an instance of the required plugin based on its name.
    """
    mgr = driver.DriverManager(
        namespace='doconv.converter',
        name=name,
        invoke_on_load=True,
    )
    return mgr.driver


def execute_plugin_chain(input_file, plugin_chain):
    """ Calls each plugin in the needed order feeding as input file
    the output file generated by the plugin previously called.
    """
    # a plugin_tuple is a 3-tuple containing: plugin_name, input_format,
    # output_format

    files_to_remove = []
    output_file = None

    for plugin_tuple in plugin_chain:
        converter = get_converter(plugin_tuple[0])

        tmp_output_filename = append_random_suffix(input_file)
        output_file = converter.convert(input_file, plugin_tuple[1],
                                        plugin_tuple[2], tmp_output_filename)

        input_file = output_file
        files_to_remove.append(output_file)
    files_to_remove = files_to_remove[:-1]
    for document in files_to_remove:
        os.remove(document)
    return output_file


def convert(input_file, input_format, output_format, output_file=None):

    graph = create_graph()

    logger.debug("Supported formats: {0}".format(graph.nodes()))
    logger.debug("Supported format conversions: {0}".format(graph.edges()))

    if input_format not in graph.nodes():
        raise Exception("Error: Not supported input format: {0}".
                        format(input_format))
    if output_format not in graph.nodes():
        raise Exception("Error: Not supported output format: {0}".
                        format(output_format))
    if input_format == output_format:
        raise Exception("Error: Same input and output formats specified")

    # for now, simplest algorithm to choose a conversion path in the
    # conversion graph
    conversion_path = choose_best_conversion_path(
        graph, input_format, output_format)

    logger.debug(
        "Chosen chain of transformations: {0}".format(conversion_path))

    plugin_chain = get_plugin_chain(graph, conversion_path)
    logger.debug(
        "Plugins used for each transformation: {0}".format(plugin_chain))
    tmp_output_file = execute_plugin_chain(input_file, plugin_chain)

    if output_file is None:
        final_output_file_no_ext = path.splitext(
            path.basename(tmp_output_file))[0]
        output_file = final_output_file_no_ext + '.' + output_format
    shutil.move(tmp_output_file, output_file)
    print(
        "Conversion successful: file {0} generated".format(output_file))
    return output_file


def main():
    # parse CLI arguments
    arguments = docopt(__doc__, version='doconv ' + get_version())
    input_format = arguments['<input_format>']
    output_format = arguments['<output_format>']
    input_file = arguments['<file>']
    output_file = arguments['--out-file']
    verbose = arguments['--verbose']

    if verbose:
        logger.setLevel(logging.DEBUG)

    try:
        input_file_path = path.abspath(input_file)

        if output_file:
            output_file_path = path.abspath(output_file)
            convert(input_file_path, input_format, output_format,
                    output_file_path)
        else:
            convert(input_file_path, input_format, output_format)
    except Exception as e:
        if not verbose:
            print(e)
        else:
            logger.exception(e)

        sys.exit(1)


if __name__ == '__main__':
    main()
