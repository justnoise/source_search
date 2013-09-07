import os
import options

class SourceCodeFinder(object):
    def __init__(self, directory_root):
        self.directory_root = os.path.abspath(directory_root)
        self.directory_filters = []
        self.file_filters = [self.file_is_ascii,
                             self.file_is_not_too_large]
        self.add_ignore_directory('/.git')
        self.add_ignore_directory('/CVS')

    def file_is_ascii(self, filepath):
        ret_str = os.popen('file %s' % filepath).read()
        if ret_str.find('text') > -1:
            return True
        else:
            return False

    def file_is_not_too_large(self, filepath):
        return os.path.getsize(filepath) < options.max_source_file_size

    def add_ignore_directory(self, directory_name):
        def filter_func(directory_path):
            if directory_path.endswith(directory_name):
                return False
            else:
                return True
        if not directory_name.startswith('/'):
            directory_name = '/' + directory_name
        self.directory_filters.append(filter_func)

    def add_file_extension_filter(self, extension):
        def file_extension_filter(filename):
            if filename.split('.')[-1] == extension:
                return True
            else:
                return False
        if extension.startswith('.'):
            extension = extension[1:]
        self.file_filters.append(file_extension_filter)

    def all_predicates_pass(self, predicates, argument):
        return all([predicate(argument) for predicate in predicates])

    def find_sourcecode_files(self):
        print 'finding sourcecode files in %s' % self.directory_root
        source_files = []
        i = 0
        for cur_dir, dirs, files in os.walk(self.directory_root):
            if not self.all_predicates_pass(self.directory_filters, cur_dir):
                continue
            for f in files:
                filepath = cur_dir + '/' + f
                if not self.all_predicates_pass(self.file_filters, filepath):
                    continue
                print '\r%d' % i,
                i += 1
                source_files.append(filepath)
        print '\r%d files found in %s' % (i, self.directory_root)
        return source_files
