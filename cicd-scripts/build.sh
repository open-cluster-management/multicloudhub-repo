#!/bin/bash

cd $(dirname $0)
. chart-sync.sh

if [ $TRAVIS_BRANCH != "master" ] || [ $TRAVIS_BRANCH != "release-1.0.0" ]; then 
    git add ../multicloudhub/charts
    git commit -m "[skip ci] skip travis"
    git pull origin master -s recursive -X ours
    git push origin "HEAD:${TRAVIS_BRANCH}"
fi

cd ..
docker build -t $1 .
