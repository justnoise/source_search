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

from pprint import pprint
import pdb
import os
import cPickle as pickle
import time
import shelve 
import argparse

import options
import source_code_finder


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
    for col in xrange(len(data)-options.ngram_length + 1):
        cur_ngram = data[col:col+options.ngram_length]
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
        print '\rIndexing file %d of %d' % (file_id + 1, len(filepaths)),
        new_ngs = get_ngrams_in_file(f, file_id)
        all_ngs = combine_ngram_dictionaries(all_ngs, new_ngs)
    print
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
    if not os.path.exists(options.index_files_path):
        os.makedirs(options.index_files_path)
    print 'writing shelf'
    t1 = time.time()
    ngrams_file = options.index_files_path + '/ngrams.shlf'
    ngs_shelf = shelve.open(ngrams_file, flag='n', protocol=pickle.HIGHEST_PROTOCOL)
    for k, v in all_ngrams.iteritems():
        ngs_shelf[k] = v
    ngs_shelf.close()
    print 'saving indexes'
    filepath_file = options.index_files_path + '/ngram_filepaths.pkl'
    pickle.dump(filepaths, open(filepath_file, 'w'), pickle.HIGHEST_PROTOCOL)
    print 'done saving: %f seconds' % (time.time() - t1)

def load_indexes():
    filepath_file = options.index_files_path + '/ngram_filepaths.pkl'
    ngrams_file = options.index_files_path + '/ngrams.shlf'
    filepaths = pickle.load(open(filepath_file, 'r'))
    all_ngrams = shelve.open(ngrams_file, protocol=pickle.HIGHEST_PROTOCOL)
    return filepaths, all_ngrams

#-------------------------------------------------------------------------------
# Run It!
#-------------------------------------------------------------------------------
def parse_arguments():
    parser = argparse.ArgumentParser(description='Index and serach sandbox.')
    parser.add_argument('--index', '-i', nargs='+',
                        help='index source tree instead of searching.')
    parser.add_argument('search', nargs='*',
                        help='source tree for items listed on the command line.')
    args = parser.parse_args()
    return args

if __name__ == '__main__':
    args = parse_arguments()
    if args.index:
        directories = args.index
        filepaths = []
        for d in directories:
            finder = source_code_finder.SourceCodeFinder(d)
            new_filepaths = finder.find_sourcecode_files()
            filepaths.extend(new_filepaths)
        all_ngrams = get_ngrams_in_file_list(filepaths)
        save_indexes(filepaths, all_ngrams)
    else:
        filepaths, all_ngrams = load_indexes()
        # uuuh, yeah, we should validate arguments above...
        if not args.search:
            print 'You need to enter a search string:'
            print 'Usage: source_search.py <some_string>'
        search_str = ' '.join(args.search)
        print 'searching for %s' % search_str
        matching_candidates = find_matching_candidates(search_str, all_ngrams)
        grep_matching_files(search_str, matching_candidates, filepaths)
