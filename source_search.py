#!/home/shared/qa_team/opt/python/bin/python2.5

# Copyright (C) 2012 by Brendan Cox

# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:

# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.

# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
# THE SOFTWARE.

################################################################################
# source_search.py
# -----------------
# This is a utility that is useful for indexing and searching medium
# size source code repositories.
#
# To use it, first index your sandbox with:
# python source_search.py -s
#
# Indexes consume a fair amount of space but that's the price you
# pay...
#
# To search your sandbox simply enter the search terms:
# python source_search.py 'search string'
# 
# multiple word searches should be enclosed in quotes otherwise
# multiple spaces between words are interpreted as a single space.
# Yeah, I'm a bit lazy
# 
# Wildcards (*) are accepted and used in their traditional globbing
# sense however true regular expressions aren't implemented
# e.x.
# python source_search.py numto*interval
# will return matches of numtodsinterval and numtoyminterval
#
################################################################################

from pprint import pprint
import pdb
import os
import re
import cPickle as pickle
import sys
import time
import shelve 
from optparse import OptionParser

#todo: 
#----------------------------------------
# break out finding files into own module

ngram_length = 3
save_path = '/home/bcox/search_indexes'
max_source_file_size = 1000000
sandbox_directory = '/home/bcox/sandbox'
cc_directory = sandbox_directory + '/cc'

#-------------------------------------------------------------------------------
# Finding sourcecode files
#-------------------------------------------------------------------------------
def get_common_directories(common_folder_path):
    return os.listdir(common_folder_path)

def make_common_files_filter(common_directories):
    '''returns a function that tests whether a directory is a common folder'''
    def filter_func(directory_path):
        for common_directory in common_directories:
            if directory_path.endswith(common_directory):
                return False
        return True
    return filter_func

def is_scripts_directory(dir_path):
    if dir_path.endswith('/cc') or dir_path.endswith('/CVSROOT'):
        return False
    else:
        return True

def file_is_ascii(filepath):
    ret_str = os.popen('file %s' % filepath).read()
    if ret_str.find('text') > -1:
        return True
    else:
        return False

def file_is_not_too_large(filepath):
    return os.path.getsize(filepath) < max_source_file_size

def make_directory_name_filter(directory_name):
    def filter_func(directory_path):
        if directory_path.endswith(directory_name):
            return False
        else:
            return True
    return filter_func

def all_predicates_pass(predicates, argument):
    for pred in predicates:
        if not pred(argument):
            return False
    return True

def get_files_in_directory(d):
    filepaths = []
    file_filters = [file_is_ascii, file_is_not_too_large]
    directory_filters = [make_directory_name_filter('/CVS')]
    for d in directories:
        filepaths.extend(get_files(d, file_filters, directory_filters))
    return filepaths

def get_files(starting_dir, file_filters, directory_filters):
    print 'getting files in %s' % starting_dir
    starting_dir = os.path.abspath(starting_dir)
    source_files = []
    i = 0
    for root_dir, dirs, files in os.walk(starting_dir):
        if not all_predicates_pass(directory_filters, root_dir):
            continue
        for f in files:
            filepath = root_dir + '/' + f
            if not all_predicates_pass(file_filters, filepath):
                continue
            print '\r%d' % i,
            i += 1
            source_files.append(filepath)
    print '\r%d files found in %s' % (i, starting_dir)
    return source_files

def get_cc_files(cc_dir):
    #get common files
    source_files = []
    common_root_dir = cc_dir + '/common'
    file_filters = [file_is_ascii, file_is_not_too_large]
    cvs_directory_filter = [make_directory_name_filter('/CVS')]
    common_source_files = get_files(common_root_dir, file_filters, cvs_directory_filter)
    source_files.extend(common_source_files)
    #get all other directories
    common_directories = get_common_directories(common_root_dir)
    common_directory_filter = make_common_files_filter(common_directories)
    directory_filter = [make_directory_name_filter('/CVS'), common_directory_filter]
    cc_source_files = get_files(cc_dir, file_filters, directory_filter)
    source_files.extend(cc_source_files)
    return source_files

def get_scripts_files(sandbox_dir):
    dirs = os.listdir(sandbox_dir)
    dirs.sort()
    #pull out the latest version of versioned directories (e.g. scripts121 instead of scripts114
    modules_to_directories = {}
    version_re = re.compile(r'\d+$')
    for d in dirs:
        version_match = version_re.search(d)
        if not version_match:
            modules_to_directories[d] = d
        else:
            version = version_match.group()
            module = d.replace(version, '')
            modules_to_directories[module] = d
    directories = modules_to_directories.values()
    #now go through and get all the files in those directories
    source_files = []
    file_filters = [file_is_ascii, file_is_not_too_large]
    cvs_directory_filter = [make_directory_name_filter('/CVS')]
    for d in directories:
        # cc is handled by a different function, dont index CVSROOT
        d = sandbox_dir + '/' + d
        if d.endswith('/cc') or d.endswith('/CVSROOT'):
            continue
        files = get_files(d, file_filters, cvs_directory_filter)
        source_files.extend(files)
    return source_files

#-------------------------------------------------------------------------------
# ngram indexing
#-------------------------------------------------------------------------------
def combine_ngram_dictionaries(existing, new):
    for k, values in new.iteritems():
        existing.setdefault(k, list()).extend(values)
    return existing

def get_ngrams_in_string(s):
    ngs = set()
    data = s.lower()
    for col in xrange(len(data)-ngram_length + 1):
        cur_ngram = data[col:col+ngram_length]
        ngs.add(cur_ngram)
    return ngs

def get_ngrams_in_wildcard_string(s):
    ngs = set()
    search_strings = s.split('*')
    for search_string in search_strings:
        new_ngs = get_ngrams_in_string(search_string)
        ngs.update(new_ngs)
    return ngs

def get_ngrams_in_file(filepath, file_id):
    file_ngs = {}
    fp = open(filepath)
    for i_line, line in enumerate(fp.readlines()):
        stripped_line = line.strip()
        line_ngs = get_ngrams_in_string(stripped_line)
        for ng in line_ngs:
            # ngrams are stored in a packed list that looks like
            # file_ngs['foo'] = [file_1, line_1, file_X, line_x].  
            # This saves a bit of space compared to storing tuples
            # plus it ends up being a big faster
            file_ngs.setdefault(ng, list()).append(file_id)
            file_ngs[ng].append(i_line)
    return file_ngs

def get_ngrams_in_file_list(filepaths):
    all_ngs = {}
    for file_id, f in enumerate(filepaths):
        print '\rIndexing file %d of %d' % (file_id, len(filepaths)),
        new_ngs = get_ngrams_in_file(f, file_id)
        all_ngs = combine_ngram_dictionaries(all_ngs, new_ngs)
    return all_ngs

def unpack_list(lst):
    unpacked = set()
    for i in xrange(0, len(lst), 2):
        v1 = lst[i]
        v2 = lst[i+1]
        unpacked.add((v1, v2))
    return unpacked

# to search for ngrams
# break the string up into ngrams and find all matches
# then find the intersections of all those matches
def find_matching_candidates(search_str, ngrams):
    matches_all_items = None
    target_ngs = get_ngrams_in_wildcard_string(search_str);
    for ng in target_ngs:
        try:
            item_files_and_lines = unpack_list(ngrams[ng])            
            #item_files_and_lines = set(ngrams[ng])
            if matches_all_items is None:
                matches_all_items = item_files_and_lines
            else:
                matches_all_items = matches_all_items.intersection(item_files_and_lines)
        except KeyError:
            print 'whoops!'
            return []
    return list(matches_all_items)

def print_matching_file_lines(matching_candidates, filepaths):
    for file_id, line_number in sorted(matching_candidates):
        filepath = filepaths[file_id]
        command = "sed -n '%dp' %s" % (line_number+1, filepath)
        line_data = os.popen(command).read()
        line_data = line_data.strip()
        print '%s (%d): %s' % (filepath, line_number+1, line_data)

def grep_matching_files(search_str, matching_candidates, filepaths):
    file_ids = set([file_id for file_id, line_number in matching_candidates])
    search_str = search_str.replace('*', '.*')
    for file_id in file_ids:
        filepath = filepaths[file_id]
        command = "grep --with-filename -i '%s' %s" % (search_str, filepath)
        line_data = os.popen(command).read()
        line_data = line_data.strip()
        if line_data:
            print '%s' % (line_data)
        
#-------------------------------------------------------------------------------
# Serialization
#-------------------------------------------------------------------------------
def save_indexes(filepaths, all_ngrams):
    print 'writing shelf'
    t1 = time.time()
    ngrams_file = save_path + '/ngrams.shlf'
    ngs_shelf = shelve.open(ngrams_file, flag='n', protocol=pickle.HIGHEST_PROTOCOL)
    for k, v in all_ngrams.iteritems():
        ngs_shelf[k] = v
    ngs_shelf.close()
    print 'saving indexes'
    filepath_file = save_path + '/ngram_filepaths.pkl'
    pickle.dump(filepaths, open(filepath_file, 'w'), pickle.HIGHEST_PROTOCOL)
    print 'done saving: %f seconds' % (time.time() - t1)

def load_indexes():
    filepath_file = save_path + '/ngram_filepaths.pkl'
    ngrams_file = save_path + '/ngrams.shlf'
    filepaths = pickle.load(open(filepath_file, 'r'))
    all_ngrams = shelve.open(ngrams_file, protocol=pickle.HIGHEST_PROTOCOL)
    return filepaths, all_ngrams

#-------------------------------------------------------------------------------
# Run It!
#-------------------------------------------------------------------------------
def parse_arguments():
    parser = OptionParser()
    parser.add_option("-i", "--index", dest="index", action='store_true',
                      help="index the specified directories")
    parser.add_option("-s", "--index-sandbox", dest="index_sandbox", action='store_true',
                      help="index the entire sandbox")
    options, args = parser.parse_args()
    # todo, validate arguments here
    return options, args

if __name__ == '__main__':
    options, args = parse_arguments()
    if options.index:
        print args
        directories = args
        filepaths = get_files_in_directory(directories)
        all_ngrams = get_ngrams_in_file_list(filepaths)
        save_indexes(filepaths, all_ngrams)
    elif options.index_sandbox:
        scripts_files = get_scripts_files(sandbox_directory)
        cc_files = get_cc_files(cc_directory)
        filepaths = cc_files
        filepaths.extend(scripts_files)
        all_ngrams = get_ngrams_in_file_list(filepaths)
        save_indexes(filepaths, all_ngrams)
    else:
        filepaths, all_ngrams = load_indexes()
        # uuuh, yeah, we should validate arguments above...
        if not args:
            print 'You need to enter a search string:'
            print 'Usage: source_search.py <some_string>'
        search_str = ' '.join(args)
        print 'searching for %s' % search_str
        matching_candidates = find_matching_candidates(search_str, all_ngrams)
        grep_matching_files(search_str, matching_candidates, filepaths)
