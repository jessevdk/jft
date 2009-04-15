#!/bin/sh

shared=$HOME/.local/share

mkdir -p $shared/gtksourceview-2.0
mkdir -p $shared/gtksourceview-2.0/language-specs
mkdir -p $shared/gtksourceview-2.0/styles
mkdir -p $shared/mime/packages
mkdir -p $HOME/.gnome2/gedit/plugins

# Copy language and style
cp -rf gtksourceview-2.0/styles/* $shared/gtksourceview-2.0/styles/
cp -rf gtksourceview-2.0/language-specs/* $shared/gtksourceview-2.0/language-specs/

# Copy plugin
cp -rf plugin/* $HOME/.gnome2/gedit/plugins/

# Install mime
cp -rf mime/* $shared/mime/packages/
update-mime-database $shared/mime
