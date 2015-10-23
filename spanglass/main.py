#!/usr/bin/env python2

""" This is the main CLI app for spanglass """

from .web_server import ThreadingHTTPServer
import hashlib
import formic
from cement.core.controller import CementBaseController, expose
from six.moves import configparser
from cement.core.foundation import CementApp
import os
import mimetypes
import boto
import boto.s3.connection
import boto.cloudfront
import boto.s3.key
import boto.exception


class SpanGlassController(CementBaseController):
    """ This is the Spanglass controller with all the subcommands """
    class Meta(object):
        # pylint: disable=C0111
        label = 'base'
        config_files = [os.path.join(os.getcwd(), 'spanglass.ini')]
        description = 'SpanGlass'
        arguments = [
            (['extra_arguments'],
             dict(action='store', nargs='*')),
            (['--force'],
             dict(action='store_true')),
        ]

    @expose(hide=True)
    def default(self):
        # pylint: disable=C0111
        self.app.args.print_help()

    @expose(help='Create a new application w/ s3 buckets')
    def create(self):
        # pylint: disable=C0111
        try:
            conn = self.app.S3Connection()
        except boto.exception.NoAuthHandlerFound:
            raise ValueError(
                'No credentials set up, run "aws configure" first')
        name = raw_input('What is the name of your app? [%s] ' % (
            os.path.basename(os.getcwd()),)) or os.path.basename(os.getcwd())
        root = raw_input(
            'What is the root directory to get files from? [.] ') or '.'
        bucket_names = dict()
        for env in ('development', 'staging', 'production'):
            bucket_created = False
            while not bucket_created:
                bucket_names[env] = raw_input('What would you like to name the bucket for your %s environment in s3? [%s] ' % (
                    env, env + '-www.' + name + '.com')) or env + '-www.' + name + '.com'
                try:
                    conn.create_bucket(bucket_names[env])
                    bucket_created = True
                except boto.exception.S3CreateError:
                    bucket_created = False
        config = configparser.RawConfigParser()
        config.add_section('buckets')
        config.add_section('files')
        config.add_section('app')
        config.set('app', 'name', name)
        config.set('files', 'root', root)
        config.set('files', 'include', '**')
        config.set('files', 'ignore', 'spanglass.ini')
        config.set('buckets', 'development', bucket_names['development'])
        config.set('buckets', 'staging', bucket_names['staging'])
        config.set('buckets', 'production', bucket_names['production'])
        with open('spanglass.ini', 'wb') as configfile:
            config.write(configfile)

    @expose(help='Initialize against existing s3 buckets')
    def init(self):
        # pylint: disable=C0111
        name = raw_input('What is the name of your app? [%s] ' % (
            os.path.basename(os.getcwd()),)) or os.path.basename(os.getcwd())
        root = raw_input(
            'What is the root directory to get files from? [.] ') or '.'
        development_bucket = raw_input('What is the name of your development bucket in s3? [%s] ' % (
            'dev-www.' + name + '.com',)) or 'dev-www.' + name + '.com'
        staging_bucket = raw_input('What is the name of your staging bucket in s3? [%s] ' % (
            'stg-www.' + name + '.com',)) or 'stg-www.' + name + '.com'
        production_bucket = raw_input('What is the name of your production bucket in s3? [%s] ' % (
            'www.' + name + '.com',)) or 'www.' + name + '.com'
        config = configparser.RawConfigParser()
        config.add_section('buckets')
        config.add_section('files')
        config.add_section('app')
        config.set('app', 'name', name)
        config.set('files', 'root', root)
        config.set('buckets', 'development', development_bucket)
        config.set('buckets', 'staging', staging_bucket)
        config.set('buckets', 'production', production_bucket)
        with open('spanglass.ini', 'wb') as configfile:
            config.write(configfile)

    @expose(help='Deploy the app\n\tUsage: spanglass deploy <environment>')
    def deploy(self):
        # pylint: disable=C0111
        env = 'development'
        if self.app.pargs.extra_arguments:
            env = self.app.pargs.extra_arguments[0]
        if env not in ('development', 'staging', 'production'):
            raise ValueError(
                'Invalid environment -- only development, staging, and production are available')
        try:
            bucket = self.app.config.get('buckets', env)
            self.__deploy_to_bucket(
                bucket, self.app.config.get('files', 'root'), env)
        except configparser.NoSectionError:
            raise ValueError(
                "No config file. Try running spanglass init or spanglass create first.")

    @expose(help='Local development server\n\tUsage: spanglass server <port>')
    def server(self):
        # pylint: disable=C0111
        port = 8080
        if self.app.pargs.extra_arguments:
            port = int(self.app.pargs.extra_arguments[0])
        root = '.'
        try:
            root = self.app.config.get('files', 'root')
        except configparser.Error:
            pass
        http_server = ThreadingHTTPServer(port=port, serve_path=root)
        print("Listening on %d" % (port,))
        http_server.serve_forever()

    @expose(help='Deploy the app')
    def promote(self):
        # pylint: disable=C0111
        source_env = 'development'
        dest_env = 'staging'
        if self.app.pargs.extra_arguments:
            source_env = self.app.pargs.extra_arguments[0]
            dest_env = self.app.pargs.extra_arguments[1]
        if source_env not in ('development', 'staging', 'production'):
            raise ValueError(
                'Invalid environment -- only development, staging, and production are available')
        if dest_env not in ('development', 'staging', 'production'):
            raise ValueError(
                'Invalid environment -- only development, staging, and production are available')
        try:
            conn = self.app.S3Connection()
        except boto.exception.NoAuthHandlerFound:
            raise ValueError(
                'No credentials set up, run "aws configure" first')
        source_bucket = conn.get_bucket(
            self.app.config.get('buckets', source_env))
        dest_bucket = conn.get_bucket(self.app.config.get('buckets', dest_env))
        for key in source_bucket.get_all_keys():
            self.app.log.info('Copying %s from %s to %s' %
                              (key.key, source_env, dest_env))
            existing_key = dest_bucket.get_key(key.key)
            if existing_key:
                source_hash = source_bucket.get_key(
                    key.key).get_metadata('hash')
                dest_hash = existing_key.get_metadata('hash')
                if source_hash == dest_hash and not self.app.pargs.force:
                    self.app.log.info(
                        '%s exists and is current, skipping' % (key.key,))
                    continue
                else:
                    dest_bucket.delete_key(key.key)
            mime = mimetypes.guess_type(key.key)[0]
            options = {'Content-Type': mime}
            if dest_env != 'production':
                options['X-Robots-Tag'] = 'noindex'
            else:
                options['X-Robots-Tag'] = 'all'
            metadata = dict(hash=source_bucket.get_key(
                key.key).get_metadata('hash'))
            metadata['x-robots-tag'] = options['X-Robots-Tag']
            dest_bucket.copy_key(key.key, source_bucket.name,
                                 key.key, headers=options, metadata=metadata, preserve_acl=True)

        for key in dest_bucket.get_all_keys():
            if key.key not in [src_key.key for src_key in source_bucket.get_all_keys()]:
                key.delete()
        print("Promoted %s to %s" % (source_env, dest_env))

    def __deploy_to_bucket(self, bucket_name, deploy_dir, env):
        # pylint: disable=C0111
        try:
            conn = self.app.S3Connection()
        except boto.exception.NoAuthHandlerFound:
            raise ValueError(
                'No credentials set up, run "aws configure" first')
        bucket = conn.get_bucket(bucket_name)
        keys_done = []
        ignore_list = ['spanglass.ini']
        include_list = ['**']
        try:
            include_list = [path.strip() for path in self.app.config.get(
                'files', 'include').split(',') if path.strip() != '']
            ignore_list = [path.strip() for path in self.app.config.get(
                'files', 'ignore').split(',') if path.strip() != '']
        except configparser.NoOptionError:
            pass
        fileset = formic.FileSet(include=include_list,
                                 exclude=ignore_list, directory=deploy_dir)
        for filename in fileset:
            src_path = filename
            dst_path = os.path.relpath(filename, deploy_dir)
            with open(filename, 'rb') as src_fh:
                source_hash = hashlib.sha512(src_fh.read()).hexdigest()
            existing_key = bucket.get_key(dst_path)
            if existing_key:
                remote_hash = existing_key.get_metadata('hash')
                if source_hash != remote_hash and not self.app.pargs.force:
                    bucket.delete_key(dst_path)
                else:
                    self.app.log.info('Skipping %s - no change' % (dst_path,))
                    keys_done.append(dst_path)
                    continue
            self.app.log.info('Uploading %s' % (dst_path,))
            s3_file = boto.s3.key.Key(bucket)
            s3_file.key = dst_path
            keys_done.append(s3_file.key)
            s3_file.set_metadata('hash', source_hash)
            mime = mimetypes.guess_type(filename)[0]
            options = {'Content-Type': mime}
            if env != 'production':
                options['X-Robots-Tag'] = 'noindex'
            else:
                options['X-Robots-Tag'] = 'all'
            s3_file.set_contents_from_filename(
                src_path, options)
            s3_file.set_acl('public-read')
        all_keys = bucket.list()
        to_delete = list(set([key.key for key in all_keys]) - set(keys_done))
        bucket.delete_keys(to_delete)
        try:
            cfconn = self.app.CloudFrontConnection()
            for dist in cfconn.get_all_distributions():
                if dist.get_distribution().config.origin.dns_name == bucket_name + '.s3.amazonaws.com':
                    cfconn.create_invalidation_request(
                        dist.id, ['/' + key for key in keys_done])
        except (boto.exception.NoAuthHandlerFound, boto.exception.BotoServerError, boto.exception.BotoClientError):
            pass


class SpanGlass(CementApp):
    """ This is the spanglass cement app. You can override the boto libraries to use mock here. """
    S3Connection = boto.s3.connection.S3Connection
    CloudFrontConnection = boto.cloudfront.CloudFrontConnection

    class Meta(object):
        # pylint: disable=C0111
        label = 'spanglass'
        base_controller = SpanGlassController
        config_files = [os.path.join(os.getcwd(), 'spanglass.ini')]
        catch_signals = []


def main():
    # pylint: disable=C0111
    with SpanGlass() as app:
        app.run()
if __name__ == '__main__':
    main()
