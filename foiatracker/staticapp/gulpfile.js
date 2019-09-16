var gulp = require('gulp'),
    jshint = require('gulp-jshint'),
    sass = require('gulp-sass'),
    concat = require('gulp-concat'),
    requirejsOptimize = require('gulp-requirejs-optimize'),
    sourcemaps = require('gulp-sourcemaps'),
    browserify = require('browserify'),
    source = require('vinyl-source-stream'),
    buffer = require('vinyl-buffer'),
    uglify = require('gulp-uglify'),
    gutil = require('gulp-util');



/**
 * JavaScript tasks
 */

gulp.task('jshint', function() {
    return gulp.src('src/js/**/*.js')
        .pipe(jshint())
        .pipe(jshint.reporter('default'))
        .pipe(jshint.reporter('fail'));
});

gulp.task('browserify', function () {
  // set up the browserify instance on a task basis
  var b = browserify({
    entries: './src/js/main.js',
    debug: true
  });

  return b.bundle()
    .pipe(source('scripts.js'))
    .pipe(buffer())
    .pipe(sourcemaps.init({loadMaps: true}))
        .pipe(uglify())
        .on('error', gutil.log)
    .pipe(sourcemaps.write('./'))
    .pipe(gulp.dest('../static/foiatracker/js/'));
});


/**
 * CSS tasks
 */

gulp.task('scss', function () {
    /* See https://github.com/sass/node-sass#options */
    var scssOpts = {
        outputStyle: 'compressed',
        includePaths: [
            './bower_components/bootstrap-sass/assets/stylesheets' // for concise imports in our _custom-bootstrap.scss
        ]
    };

    return gulp.src('./src/scss/**/*.scss')
        .pipe(sourcemaps.init())
        .pipe(sass(scssOpts).on('error', sass.logError))
        .pipe(sourcemaps.write('.', {
            sourceMappingURLPrefix: ''
        }))
        .pipe(gulp.dest('../static/foiatracker/css'));
});


/**
 * Meta/grouped tasks
 */

gulp.task('build-scripts', ['jshint', 'browserify']);
gulp.task('build-styles', ['scss']);

gulp.task('build', ['build-scripts', 'build-styles']);

gulp.task('default', ['build'], function () {
    gulp.watch('./src/js/**/*.js', ['build-scripts']);
    gulp.watch('./src/scss/**/*.scss', ['build-styles']);
});
